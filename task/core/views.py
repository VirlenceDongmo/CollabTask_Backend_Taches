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
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)



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
        # Récupérer l'email de l'utilisateur assigné
        user_email = None
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
            except Exception as e:
                print(f"Échec de la récupération de l'email de l'utilisateur: {e}")
                return

        producer = NotificationProducer()

        notification_data = {
            'event_type': 'tâche créée' if is_creation else 'tâche mise à jour',
            'task_id': str(task.id),
            'task_title': task.titre,
            'description': task.description,
            'due_date': str(task.echeance) if task.echeance else None,
            'assigned_to': task.collaborateur_id if task.collaborateur_id else None,
            'assigned_to_email': user_email,
        }
        producer.send_notification(notification_data)




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

    def _send_task_update_notification(self, task, event_type, initiator):
        """Send general update notification."""
        producer = NotificationProducer()
        assigned_email = self._get_user_email(task.collaborateur_id)
        admin_emails = self._get_admin_emails()

        # Create recipients list, avoiding duplicates
        recipients = []
        if assigned_email:
            recipients.append(assigned_email)
        recipients.extend([email for email in admin_emails if email and email not in recipients])

        notification_data = {
            'event_type': event_type,
            'task_id': str(task.id),
            'task_title': task.titre,
            'initiator_id': str(initiator.id) if initiator.id else None,
            'initiator_name': initiator.nom if initiator.nom else 'Inconnu',
            'assigned_to': str(task.collaborateur_id) if task.collaborateur_id else None,
            'assigned_to_email': assigned_email,
            'projet_id': str(task.projet_id.id) if task.projet_id else None,
            'changes': {
                'titre': task.titre,
                'description': task.description,
                'difficulte': task.difficulte,
                'statut': task.statut,
                'echeance': task.echeance.isoformat() if task.echeance else None,
                'assigned_to': str(task.collaborateur_id) if task.collaborateur_id else None,
                'projet_id': str(task.projet_id.id) if task.projet_id else None,
            },
            'recipients': recipients,
        }

        try:
            producer.send_notification(notification_data)
        except Exception as e:
            print(f"Erreur envoi notification mise à jour: {str(e)}")

    def _send_status_change_notification(self, task, old_status, new_status, initiator):
        """Send status change notification."""
        producer = NotificationProducer()
        assigned_email = self._get_user_email(task.collaborateur_id)
        admin_emails = self._get_admin_emails()

        # Create recipients list, avoiding duplicates
        recipients = []
        if assigned_email:
            recipients.append(assigned_email)
        recipients.extend([email for email in admin_emails if email and email not in recipients])

        notification_data = {
            'event_type': 'statut modifié',
            'task_id': str(task.id),
            'task_title': task.titre,
            'old_status': old_status,
            'new_status': new_status,
            'initiator_id': str(initiator.id) if initiator.id else None,
            'initiator_name': initiator.nom if initiator.username else 'Unknown',
            'assigned_to': str(task.collaborateur_id) if task.collaborateur_id else None,
            'assigned_to_email': assigned_email,
            'projet_id': str(task.projet_id.id) if task.projet_id else None,
            'priority': 'high',
            'recipients': recipients,
        }

        try:
            producer.send_notification(notification_data)
        except Exception as e:
            print(f"Erreur envoi notification statut: {str(e)}")



# class UpdateTaskView(generics.UpdateAPIView):
#     queryset = Task.objects.all()
#     serializer_class = TaskSerializer

#     def perform_update(self, serializer):
#         instance = self.get_object()
#         old_data = {
#             'assigned_to': instance.assigned_to,
#             'title': instance.title,
#             'status': instance.status,
#             'description': instance.description,
#             'due_date': instance.due_date
#         }

#         updated_task = serializer.save()
#         current_user = self.request.user

#         # 1. Notification pour l'assigné si changement important
#         if (old_data['assigned_to'] != updated_task.assigned_to or 
#             old_data['title'] != updated_task.title or 
#             old_data['description'] != updated_task.description or
#             old_data['due_date'] != updated_task.due_date):

#             self._send_task_update_notification(
#                 task=updated_task,
#                 event_type='tache modifiée',
#                 initiator=current_user
#             )

#         # 2. Notification spéciale pour les admins si changement de statut
#         if old_data['status'] != updated_task.status:
#             self._send_status_change_notification(
#                 task=updated_task,
#                 old_status=old_data['status'],
#                 new_status=updated_task.status,
#                 initiator=current_user
#             )

#     def _send_task_update_notification(self, task, event_type, initiator):
#         """Notification générale de mise à jour"""
#         producer = NotificationProducer()
        
#         try:
#             # Récupérez les emails des utilisateurs
#             try:
#                 # Récupération de l'email de l'assigné
#                 response = requests.get(
#                     f'{settings.USER_SERVICE_URL}/api/user/{task.assigned_to}/',
#                     headers={
#                         'Authorization': self.request.headers.get('Authorization'),
#                         'Content-Type': 'application/json'
#                     },
#                     timeout=2
#                 )
#                 assigned_user_data = response.json()
#                 assigned_email = assigned_user_data.get('email')  # Extraction de l'email

#                 # Récupération de l'email du créateur/admin
#                 response = requests.get(
#                     f'{settings.USER_SERVICE_URL}/api/user/ADMIN/',
#                     headers={
#                         'Authorization': self.request.headers.get('Authorization'),
#                         'Content-Type': 'application/json'
#                     },
#                     timeout=2
#                 )
#                 admin_data = response.json()
#                 admin_email = admin_data.get('email')  # Extraction de l'email

#             except Exception as e:
#                 print(f"Failed to get user email: {e}")
#                 return

#             # Création de la liste des destinataires (uniquement les emails valides)
#             recipients = []
#             if assigned_email:
#                 recipients.append(assigned_email)
#             if admin_email and admin_email != assigned_email:  # Éviter les doublons
#                 recipients.append(admin_email)
            
#             notification_data = {
#                 'event_type': event_type,
#                 'task_id': str(task.id),
#                 'task_title': task.title,
#                 'initiator_id': initiator.id,
#                 'initiator_name': initiator.username,
#                 'assigned_to': str(task.assigned_to) if task.assigned_to else None,
#                 'assigned_to_email': assigned_email,
#                 'created_by': str(task.created_by) if task.created_by else None,
#                 'changes': {
#                     'assigned_to': str(task.assigned_to) if task.assigned_to else None,
#                     'title': task.title,
#                     'description': task.description,
#                     'due_date': task.due_date.isoformat() if task.due_date else None
#                 }
#             }
            
#             producer.send_notification(notification_data)
#         except Exception as e:
#             print(f"Erreur envoi notification mise à jour: {str(e)}")

#     def _send_status_change_notification(self, task, old_status, new_status, initiator):
#         """Notification spécifique pour changement de statut"""
#         producer = NotificationProducer()
        
#         try:
#             # Récupération de l'email de l'assigné
#             assigned_email = None
#             if task.assigned_to:

#                 try:
#                     response = requests.get(
#                         f"{settings.USER_SERVICE_URL}/api/user/{task.assigned_to}/",
#                         headers={
#                             'Authorization': self.request.headers.get('Authorization'),
#                             'Content-Type': 'application/json'
#                         },
#                         timeout=2
#                     )
                    
#                     user_data = response.json()
#                     user_email = user_data.get('email')  # Extraction de l'email
                    
#                 except Exception as e:
#                     print(f"Failed to get user email: {e}")

#                 assigned_email = user_email
            
#             # Récupération de l'email du créateur/admin
#             try:
#                 response = requests.get(
#                     f'{settings.USER_SERVICE_URL}/api/user/ADMIN/',
#                     headers={
#                         'Authorization': self.request.headers.get('Authorization'),
#                         'Content-Type': 'application/json'
#                     },
#                     timeout=2
#                 )
#                 admin_data = response.json()
#                 admin_email = admin_data.get('email')  # Extraction de l'email

#             except Exception as e:
#                 print(f"Failed to get user email: {e}")
#                 return
            
            
#             # Construction de la liste des destinataires
#             recipients = []
#             if assigned_email:
#                 recipients.append(assigned_email)
            
            
#             notification_data = {
#                 'event_type': 'statut modifié',
#                 'task_id': str(task.id),
#                 'task_title': task.title,
#                 'old_status': old_status,
#                 'new_status': new_status,
#                 'initiator_id': initiator.id,
#                 'initiator_name': initiator.username,
#                 'assigned_to': task.assigned_to if task.assigned_to else None,
#                 'assigned_to_email': assigned_email,
#                 'admin_recipients': admin_email,
#                 'priority': 'high'
#             }
            
#             producer.send_notification(notification_data)
#         except Exception as e:
#             print(f"Erreur envoi notification statut: {str(e)}")

#     def _get_user_email(self, user_id):
#         """Récupère l'email d'un utilisateur"""
#         try:
#             response = requests.get(
#                 f"{settings.USER_SERVICE_URL}/api/user/{user_id}/",
#                 headers={
#                     'Authorization': self.request.headers.get('Authorization'),
#                     'Content-Type': 'application/json'
#                 },
#                 timeout=2
#             )
#             return response.json().get('email')
#         except Exception as e:
#             print(f"Failed to get user email: {e}")
#             return None



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
                "assigned_to_email" : _get_user_email(self, user_id),
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

    
