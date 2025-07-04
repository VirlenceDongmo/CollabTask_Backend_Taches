from datetime import datetime
import requests
from rest_framework import generics,permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Task, Project
from .serializers import TaskSerializer, ProjectSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings
from rest_framework.exceptions import ValidationError
from django.core.mail import send_mail
import pika
import json
from .producteurs import NotificationProducer
from rest_framework import status
from django.core.exceptions import PermissionDenied
import logging
logger = logging.getLogger(__name__)




class ProjectListView(generics.ListAPIView):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    


class DetailTaskView(generics.RetrieveAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)



logger = logging.getLogger(__name__)

class CreateTaskView(generics.CreateAPIView):
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        collaborateur_id = serializer.validated_data.get('collaborateur_id')

        # Validation de l'utilisateur assigné (optionnel)
        if collaborateur_id:
            try:
                response = requests.get(
                    f'{settings.USER_SERVICE_URL}/api/user/{collaborateur_id}/',
                    headers={
                        'Authorization': self.request.headers.get('Authorization'),
                        'Content-Type': 'application/json'
                    },
                    timeout=2
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise ValidationError({'collaborateur_id': f"Erreur de validation utilisateur: {str(e)}"})

        # Création de la tâche
        task = serializer.save()

        # Envoi de la notification via RabbitMQ
        self._send_task_notification(task, is_creation=True)

    def _send_task_notification(self, task, is_creation):
        # Récupérer l'email et les informations de l'utilisateur assigné
        user_email = None
        user_nom = 'Inconnu'
        if task.collaborateur_id:
            try:
                response = requests.get(
                    f'{settings.USER_SERVICE_URL}/api/user/{task.collaborateur_id}/',
                    headers={
                        'Authorization': self.request.headers.get('Authorization'),
                        'Content-Type': 'application/json'
                    },
                    timeout=2
                )
                response.raise_for_status()
                user_data = response.json()
                user_email = user_data.get('email')
                user_nom = user_data.get('nom', 'Inconnu')
            except Exception as e:
                logger.error(f"Échec de la récupération des données de l'utilisateur {task.collaborateur_id}: {str(e)}")

        # Récupérer les informations de l'initiateur (utilisateur connecté)
        initiator_id = self.request.user.id if self.request.user.is_authenticated else None
        initiator_nom = self.request.user.nom if self.request.user.is_authenticated else 'Inconnu'

        # Construire le contenu de la notification
        contenu = (
            f"Nouvelle tâche créée : {task.titre}\n"
            f"Description : {task.description}\n"
            f"Échéance : {task.echeance if task.echeance else 'Non spécifiée'}\n"
            f"Assignée à : {user_nom}\n"
            f"Projet : {task.projet_id.name if task.projet_id else 'Non spécifié'}"
        )

        # Données de la notification pour RabbitMQ
        notification_data = {
            'event_type': 'tâche créée' if is_creation else 'tâche mise à jour',
            'type': 'Tâche',
            'contenu': contenu,
            'destinataire': task.collaborateur_id if task.collaborateur_id else None,
            'destinateur': initiator_id,
            'tache': str(task.id),
            'send_email': True if user_email else False,
            'recipient': user_email,
            'subject': f"{'Nouvelle tâche' if is_creation else 'Mise à jour de tâche'} : {task.titre}", 
            'task_title':task.titre,
            'assigned_to':task.collaborateur_id if task.collaborateur_id else None,
            'assigned_to_email': user_email,
            'due_date': str(task.echeance) if task.echeance else None,
            'task_id':task.id,
            'description':task.description
        }

        # Envoi de la notification via RabbitMQ
        try:
            producer = NotificationProducer()
            if producer.send_notification(notification_data):
                logger.info(f"Notification envoyée via RabbitMQ pour la tâche {task.id}")
            else:
                logger.warning(f"Échec de l'envoi via RabbitMQ pour la tâche {task.id}, tentative de fallback")
                self._send_fallback_email(notification_data)
        except Exception as e:
            logger.error(f"Erreur RabbitMQ pour la tâche {task.id}: {str(e)}")
            # Envoi direct en fallback
            self._send_fallback_email(notification_data)

    def _send_fallback_email(self, notification_data):
        """Envoyer un email en cas d'échec de RabbitMQ"""
        if not notification_data.get('recipient'):
            logger.warning("Aucun email destinataire fourni pour le fallback")
            return

        try:
            send_mail(
                subject=notification_data['subject'],
                message=notification_data['contenu'],
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification_data['recipient']],
                fail_silently=False
            )
            logger.info(f"Email de fallback envoyé à {notification_data['recipient']}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'email de fallback: {str(e)}")




class TaskListView(APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request):
        tasks = Task.objects.all()
        serializer = TaskSerializer(tasks, many=True)
        return Response({
            'success': True,
            'results': serializer.data  
        })


class CurrentUserTasksView(generics.ListAPIView):
    serializer_class = TaskSerializer

    def get_queryset(self):
        auth_header = self.request.headers.get('Authorization')
        logger.debug(f"Authorization header: {auth_header}")
        if not auth_header:
            raise ValidationError({'detail': "En-tête Authorization manquant."})

        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/current-user/',
                headers={
                    'Authorization': auth_header,
                    'Content-Type': 'application/json'
                },
                timeout=2
            )
            response.raise_for_status()
            user_data = response.json()
            logger.debug(f"User service response: {user_data}")
            user_id = user_data.get('id')
            if user_id is None:
                raise ValidationError({'detail': "L'ID de l'utilisateur n'est pas présent dans la réponse du service utilisateur."})
        except requests.RequestException as e:
            logger.error(f"Erreur de récupération de l'utilisateur actuel: {str(e)}")
            raise ValidationError({'detail': f"Erreur de récupération de l'utilisateur actuel: {str(e)}"})
        logger.debug(f"Filtering tasks for collaborateur_id: {str(user_id)}")
        return Task.objects.filter(collaborateur_id=str(user_id))



class UserTaskListView(generics.ListAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        current_user = self.request.user
        assigned_to = current_user.id
        filtered_qs = qs.filter(collaborateur_id=assigned_to)
        print(f"UserTaskListView - Fetching tasks for user {current_user.id}: {filtered_qs.count()} tasks found")
        return filtered_qs



logger = logging.getLogger(__name__)

class UpdateTaskView(generics.UpdateAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    lookup_field = 'pk'

    def perform_update(self, serializer):
        instance = self.get_object()
        current_user = self.request.user
        is_regular_user = getattr(current_user, 'role', None) == 'USER'

        # Store old data for comparison
        old_data = {
            'titre': instance.titre,
            'description': instance.description,
            'difficulte': instance.difficulte,
            'statut': instance.statut,
            'echeance': instance.echeance,
            'collaborateur_id': instance.collaborateur_id,
            'projet_id': instance.projet_id.id if instance.projet_id else None,
        }

        # Restrict fields for regular users
        if is_regular_user:
            validated_data = serializer.validated_data
            for field in ['titre', 'description', 'difficulte', 'echeance', 'collaborateur_id', 'projet_id']:
                if field in validated_data and validated_data[field] != old_data[field]:
                    raise ValidationError({field: "Les utilisateurs réguliers ne peuvent modifier que le statut."})

        # Save updated task
        updated_task = serializer.save()

        # Send notifications
        # 1. General update notification if significant fields changed
        if any(
            old_data[field] != getattr(updated_task, field)
            for field in ['titre', 'description', 'difficulte', 'echeance', 'collaborateur_id']
        ) or (old_data['projet_id'] != (updated_task.projet_id.id if updated_task.projet_id else None)):
            self._send_task_update_notification(
                task=updated_task,
                event_type='tâche modifiée',
                initiator=current_user,
            )

        # 2. Status change notification
        if old_data['statut'] != updated_task.statut:
            self._send_status_change_notification(
                task=updated_task,
                old_status=old_data['statut'],
                new_status=updated_task.statut,
                initiator=current_user,
            )

    def _get_user_email(self, user_id):
        """Retrieve user email by ID."""
        if not user_id:
            return None
        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/{user_id}/',
                headers={
                    'Authorization': self.request.headers.get('Authorization'),
                    'Content-Type': 'application/json',
                },
                timeout=2,
            )
            response.raise_for_status()
            return response.json().get('email')
        except Exception as e:
            logger.error(f"Failed to get user email for ID {user_id}: {e}")
            return None

    def _get_admin_emails(self):
        """Retrieve emails of all admin users."""
        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/list/',
                headers={
                    'Authorization': self.request.headers.get('Authorization'),
                    'Content-Type': 'application/json',
                },
                timeout=2,
            )
            response.raise_for_status()
            users = response.json()
            return [user['email'] for user in users if user.get('role') == 'ADMIN' and user.get('email')]
        except Exception as e:
            logger.error(f"Failed to get admin emails: {e}")
            return []

    def _send_task_update_notification(self, task, event_type, initiator):
        """Send general update notification."""
        # Récupérer l'email et le nom de l'utilisateur assigné
        assigned_email = None
        assigned_nom = 'Inconnu'
        if task.collaborateur_id:
            try:
                response = requests.get(
                    f'{settings.USER_SERVICE_URL}/api/user/{task.collaborateur_id}/',
                    headers={
                        'Authorization': self.request.headers.get('Authorization'),
                        'Content-Type': 'application/json',
                    },
                    timeout=2,
                )
                response.raise_for_status()
                user_data = response.json()
                assigned_email = user_data.get('email')
                assigned_nom = user_data.get('nom', 'Inconnu')
            except Exception as e:
                logger.error(f"Échec de la récupération des données de l'utilisateur {task.collaborateur_id}: {str(e)}")

        # Construire le contenu de la notification

        # Récupérer les informations de l'initiateur (utilisateur connecté)
        initiator_id = self.request.user.id if self.request.user.is_authenticated else None
        initiator_nom = self.request.user.nom if self.request.user.is_authenticated else 'Inconnu'

        contenu = (
            f"Tâche modifiée : {task.titre}\n"
            f"Description : {task.description}\n"
            f"Échéance : {task.echeance if task.echeance else 'Non spécifiée'}\n"
            f"Difficulté : {task.difficulte}\n"
            f"Assignée à : {assigned_nom}\n"
            f"Projet : {task.projet_id.name if task.projet_id else 'Non spécifié'}\n"
            f"Modifiée par : {initiator_nom}"
        )

        # Données de la notification pour RabbitMQ
        notification_data = {
            'event_type': event_type,
            'type': 'Tâche',
            'contenu': contenu,
            'destinataire': task.collaborateur_id if task.collaborateur_id else None,
            'destinateur': initiator.id if initiator.id else None,
            'tache': str(task.id),
            'send_email': True if assigned_email else False,
            'recipient': assigned_email,
            'subject': f"Tâche modifiée : {task.titre}",
            'assigned_to': task.collaborateur_id if task.collaborateur_id else None,
            'task_title' : task.titre,
            'task_id': task.id,
            'initiator_id': initiator_id,
            'assigned_to_email':assigned_email
        }

        # Envoi de la notification via RabbitMQ
        try:
            producer = NotificationProducer()
            if producer.send_notification(notification_data):
                logger.info(f"Notification envoyée via RabbitMQ pour la mise à jour de la tâche {task.id}")
            else:
                logger.warning(f"Échec de l'envoi via RabbitMQ pour la tâche {task.id}, tentative de fallback")
                self._send_fallback_email(notification_data)
        except Exception as e:
            logger.error(f"Erreur RabbitMQ pour la mise à jour de la tâche {task.id}: {str(e)}")
            # Envoi direct en fallback
            self._send_fallback_email(notification_data)

    def _send_status_change_notification(self, task, old_status, new_status, initiator):
        """Send status change notification."""
        # Récupérer l'email et le nom de l'utilisateur assigné
        assigned_email = None
        assigned_nom = 'Inconnu'
        if task.collaborateur_id:
            try:
                response = requests.get(
                    f'{settings.USER_SERVICE_URL}/api/user/{task.collaborateur_id}/',
                    headers={
                        'Authorization': self.request.headers.get('Authorization'),
                        'Content-Type': 'application/json',
                    },
                    timeout=2,
                )
                response.raise_for_status()
                user_data = response.json()
                assigned_email = user_data.get('email')
                assigned_nom = user_data.get('nom', 'Inconnu')
            except Exception as e:
                logger.error(f"Échec de la récupération des données de l'utilisateur {task.collaborateur_id}: {str(e)}")

        # Récupérer les emails des admins
        admin_emails = self._get_admin_emails()

        # Créer la liste des destinataires, en évitant les doublons
        recipients = []
        if assigned_email:
            recipients.append(assigned_email)
        recipients.extend([email for email in admin_emails if email and email not in recipients])

        # Construire le contenu de la notification
        # Récupérer les informations de l'initiateur (utilisateur connecté)
        initiator_id = self.request.user.id if self.request.user.is_authenticated else None
        initiator_nom = self.request.user.nom if self.request.user.is_authenticated else 'Inconnu'
        contenu = (
            f"Changement de statut de la tâche : {task.titre}\n"
            f"De : {old_status}\n"
            f"À : {new_status}\n"
            f"Assignée à : {assigned_nom}\n"
            f"Projet : {task.projet_id.name if task.projet_id else 'Non spécifié'}\n"
            f"Initiateur : {initiator_nom}"
        )

        # Données de la notification pour RabbitMQ
        notification_data = {
            'event_type': 'statut modifié',
            'type': 'Statut',
            'contenu': contenu,
            'destinataire': task.collaborateur_id if task.collaborateur_id else None,
            'destinateur': initiator.id if initiator.id else None,
            'tache': str(task.id),
            'send_email': True if recipients else False,
            'recipient': recipients,
            'subject': f"Changement de statut : {task.titre}",
            'priority': 'high',
            'assigned_to': task.collaborateur_id if task.collaborateur_id else None,
            'task_title' : task.titre,
            'old_status': old_status,
            'new_status': new_status,
            'initiator_name': initiator_nom,
            'task_id': task.id,
        }

        # Envoi de la notification via RabbitMQ
        try:
            producer = NotificationProducer()
            if producer.send_notification(notification_data):
                logger.info(f"Notification envoyée via RabbitMQ pour le changement de statut de la tâche {task.id}")
            else:
                logger.warning(f"Échec de l'envoi via RabbitMQ pour la tâche {task.id}, tentative de fallback")
                self._send_fallback_email(notification_data)
        except Exception as e:
            logger.error(f"Erreur RabbitMQ pour le changement de statut de la tâche {task.id}: {str(e)}")
            # Envoi direct en fallback
            self._send_fallback_email(notification_data)


    def _send_fallback_email(self, notification_data):
        """Envoyer un email en cas d'échec de RabbitMQ"""
        recipients = notification_data.get('recipient')
        if not recipients:
            logger.warning("Aucun email destinataire fourni pour le fallback")
            return

        # Gérer les cas où recipient est une liste ou une chaîne
        recipient_list = recipients if isinstance(recipients, list) else [recipients]

        try:
            send_mail(
                subject=notification_data['subject'],
                message=notification_data['contenu'],
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(set(recipient_list)),  # Évite les doublons
                fail_silently=False
            )
            logger.info(f"Email de fallback envoyé à {recipient_list}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'email de fallback: {str(e)}")



class DeleteTaskView(generics.DestroyAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    
    lookup_field = 'pk'

    def perform_destroy(self, instance):
        current_user = self.request.user
        is_regular_user = getattr(current_user, 'role', None) == 'USER'

        # Restrict deletion to admins only
        if is_regular_user:
            raise PermissionDenied("Seuls les administrateurs peuvent supprimer des tâches.")

        try:
            print(f"Tentative de suppression de la tâche {instance.id}")

            # Prepare task data before deletion
            task_data = {
                'id': str(instance.id),
                'titre': instance.titre,
                'assigned_to': str(instance.collaborateur_id) if instance.collaborateur_id else None,
                'projet_id': str(instance.projet_id.id) if instance.projet_id else None,
                'deleted_by': str(current_user.id) if current_user.id else None,
                'deleted_by_name': current_user.nom if current_user.username else 'Unknown',
            }

            # Fetch emails for notification
            assigned_to_email = self._get_user_email(instance.collaborateur_id)
            admin_emails = self._get_admin_emails()

            # Create recipients list, avoiding duplicates
            recipients = []
            if assigned_to_email:
                recipients.append(assigned_to_email)
            recipients.extend([email for email in admin_emails if email and email not in recipients])

            # Add recipients to task_data
            task_data['recipients'] = recipients

            # Delete the task
            instance.delete()
            print(f"Tâche {instance.id} supprimée avec succès")

            # Send deletion notification
            self._send_deletion_notification(task_data)

        except Exception as e:
            print(f"ERREUR CRITIQUE lors de la suppression de la tâche {instance.id}: {str(e)}")
            raise ValidationError(f"Erreur lors de la suppression de la tâche: {str(e)}")

    def _get_user_email(self, user_id):
        """Retrieve user email by ID."""
        if not user_id:
            return None
        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/{user_id}/',
                headers={
                    'Authorization': self.request.headers.get('Authorization'),
                    'Content-Type': 'application/json',
                },
                timeout=2,
            )
            response.raise_for_status()
            return response.json().get('email')
        except Exception as e:
            print(f"Failed to get user email for ID {user_id}: {e}")
            return None

    def _get_admin_emails(self):
        """Retrieve emails of all admin users."""
        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/list/',
                headers={
                    'Authorization': self.request.headers.get('Authorization'),
                    'Content-Type': 'application/json',
                },
                timeout=2,
            )
            response.raise_for_status()
            users = response.json()
            return [user['email'] for user in users if user.get('role') == 'ADMIN' and user.get('email')]
        except Exception as e:
            print(f"Failed to get admin emails: {e}")
            return []

    def _send_deletion_notification(self, task_data):
        """Send notification for task deletion."""
        try:
            print(f"Préparation notification suppression: {task_data}")
            producer = NotificationProducer()
            notification_data = {
                'event_type': 'tâche supprimée',
                'task_id': task_data['id'],
                'task_title': task_data['titre'],
                'assigned_to': task_data['collaborateur_id'],
                # "assigned_to_email" : _get_user_email(self, user_id),
                'projet_id': task_data['projet_id'],
                'deleted_by': task_data['deleted_by'],
                'deleted_by_name': task_data['deleted_by_name'],
                'recipients': task_data['recipients'],
                'priority': 'high',
            }
            producer.send_notification(notification_data)
            print("Notification de suppression envoyée")
        except Exception as e:
            print(f"Erreur envoi notification suppression: {str(e)}")


# class DeleteTaskView(generics.DestroyAPIView):
#     queryset = Task.objects.all()
#     serializer_class = TaskSerializer
#     permission_classes = [AllowAny]

#     def perform_destroy(self, instance):
#         try:
#             print(f"Tentative de suppression de la tâche {instance.id}")
            
#             # Récupération des données avant suppression
#             task_data = {
#                 'id': str(instance.id),
#                 'title': instance.titre,
#                 'assigned_to': str(instance.collaborateur_id) if instance.collaborateur_id else None,
#             }
            
#             # Récupération de l'email

#             assigned_email = None
#             if instance.collaborateur_id:
#                 try:

#                     response = requests.get(
#                         f"{settings.USER_SERVICE_URL}/api/user/{instance.collaborateur_id}/",
#                         headers={
#                             'Authorization': self.request.headers.get('Authorization'),
#                             'Content-Type': 'application/json'
#                         },
#                         timeout=2
#                     )
#                     assigned_email = response.json().get('email')
#                     print(f"Email assigné récupéré: {assigned_email}")
#                 except Exception as e:
#                     print(f"Erreur récupération email: {str(e)}")

#             # Suppression effective
#             instance.delete()
#             print("Tâche supprimée avec succès")

#             # Notification
#             if assigned_email:

#                 task_data = {
#                     'task_id': task_data['id'],
#                     'task_title': task_data['titre'],
#                     'assigned_to': task_data['collaborateur_id'],
#                     'assigned_to_email': assigned_email,
#                     'deleted_by': str(self.request.user.id) if self.request.user.id else None,
#                 }

#                 self._send_deletion_notification(task_data = task_data)

#         except Exception as e:
#             print(f"ERREUR CRITIQUE lors de la suppression: {str(e)}")
#             raise  # Relance l'exception pour voir l'erreur dans l'API


#     def _send_deletion_notification(self, task_data):
#         """Version simplifiée pour le debug"""
#         try:
#             print(f"Préparation notification suppression: {task_data}")
#             producer = NotificationProducer()
#             producer.send_notification({
#                 'event_type': 'tache supprimée',
#                 **task_data
#             })
#             print("Notification envoyée")
#         except Exception as e:
#             print(f"Erreur envoi notification: {str(e)}")

    
