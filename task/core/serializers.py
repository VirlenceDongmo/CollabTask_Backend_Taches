from django.conf import settings
from rest_framework import serializers
from .models import Task, Project
import requests

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description']

class TaskSerializer(serializers.ModelSerializer):
    collaborateur_details = serializers.SerializerMethodField(read_only=True)
    projet_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        
        write_only=True
    )
    projet_details = ProjectSerializer(source='projet_id', read_only=True)
    echeance = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Task
        fields = [
            'id',
            'titre',
            'description',
            'difficulte',
            'statut',
            'echeance',
            'collaborateur_id',
            'collaborateur_details',
            'projet_id',
            'projet_details',
            'date_creation',
        ]
        extra_kwargs = {
            'date_creation': {'read_only': True},
            'collaborateur_id': {'required': False, 'allow_null': True},
            'projet_id': {'required': True, 'write_only': True},
        }

    def get_collaborateur_details(self, obj):
        if not obj.collaborateur_id:
            return None
        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/{obj.collaborateur_id}/',
                headers={'Content-Type': 'application/json'},
                timeout=2
            )
            return response.json() if response.status_code == 200 else None
        except:
            return None

    def validate_difficulte(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("La difficulté doit être comprise entre 1 et 5.")
        return value

    def validate_projet_id(self, value):
        if not Project.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Le projet spécifié n'existe pas.")
        return value

    def validate_collaborateur_id(self, value):
        if value:
            try:
                response = requests.get(
                    f'{settings.USER_SERVICE_URL}/api/user/{value}/',
                    headers={'Content-Type': 'application/json'},
                    timeout=2
                )
                if response.status_code != 200:
                    raise serializers.ValidationError("L'utilisateur spécifié n'existe pas.")
            except requests.RequestException:
                raise serializers.ValidationError("Erreur lors de la validation de l'utilisateur.")
        return value



# from django.contrib.auth.models import User
# from rest_framework import serializers
# from .models import Task, Project


# class ProjectSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Project
#         fields = ['id', 'name', 'description']


# class TaskSerializer(serializers.ModelSerializer):
#     collaborateur_id_details = serializers.SerializerMethodField(read_only=True)
#     projet_id = ProjectSerializer(read_only=True)
#     echeance = serializers.DateField(required=False, allow_null=True)

#     class Meta:
#         model = Task
#         fields = [
#             'id',
#             'titre',
#             'description',
#             'difficulte',
#             'statut',
#             'echeance',
#             'collaborateur_id',
#             'projet_id',
#             'date_creation',
#             'collaborateur_id_details',
#         ]
#         extra_kwargs = {
#             'date_creation': {'read_only': True},
#             'collaborateur_id': {'required': False, 'allow_null': True},
#             'projet_id': {'required': True},
#         }

#     def validate_difficulte(self, value):
#         if not (1 <= value <= 5):
#             raise serializers.ValidationError("La difficulté doit être comprise entre 1 et 5.")
#         return value


#     def get_collaborateur_id_details(self, obj):
#         if not obj.collaborateur_id:
#             return None
#         try:
#             response = requests.get(f'{settings.USER_SERVICE_URL}/api/user/{obj.collaborateur_id}/')
#             return response.json() if response.status_code == 200 else None
#         except:
#             return None




# from django.conf import settings
# from rest_framework import serializers
# from .services import auth_services
# from .models import Task
# import requests  # Pour faire des appels à l'autre projet Django



# class TaskSerializer(serializers.ModelSerializer):
#     assigned_to_details = serializers.SerializerMethodField(read_only=True)
#     due_date = serializers.DateField(required=False, allow_null=True)

#     class Meta:
#         model = Task
#         fields = '__all__'  # Utilisez tous les champs ou listez-les explicitement
#         extra_kwargs = {
#             'created_by': {'read_only': True},
#             'assigned_to': {'required': False}
#         }

#     def get_assigned_to_details(self, obj):
#         if not obj.assigned_to:
#             return None
#         try:
#             response = requests.get(f'{settings.USER_SERVICE_URL}/api/user/{obj.assigned_to}/')
#             return response.json() if response.status_code == 200 else None
#         except:
#             return None
        