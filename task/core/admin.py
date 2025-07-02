from django.conf import settings
from django.contrib import admin
from .models import Task, Project
import requests

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'date_creation', 'date_modification')
    search_fields = ('name', 'description')
    list_filter = ('date_creation', 'date_modification')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'titre',
        'description',
        'difficulte',
        'statut',
        'echeance',
        'get_collaborateur_username',
        'projet_id',
        'date_creation',
    )
    search_fields = ('titre', 'description')
    list_filter = ('statut', 'difficulte', 'projet_id', 'date_creation')
    list_editable = ('statut', 'difficulte', 'echeance')

    def get_collaborateur_username(self, obj):
        if not obj.collaborateur_id:
            return '-'
        try:
            response = requests.get(
                f'{settings.USER_SERVICE_URL}/api/user/{obj.collaborateur_id}/',
                headers={'Content-Type': 'application/json'},
                timeout=2
            )
            response.raise_for_status()
            user_data = response.json()
            return user_data.get('username', 'Inconnu')
        except requests.RequestException:
            return 'Erreur API'

    get_collaborateur_username.short_description = 'Collaborateur'






# from django.contrib import admin
# from .models import Task


# @admin.register(Task)
# class TaskAdmin(admin.ModelAdmin):
#     list_display = ('title', 'status', 'created_by', 'assigned_to', 'due_date')  
#     list_filter = ('status', 'created_by')  
#     search_fields = ('title', 'description') 
#     ordering = ('-created_at',) 

