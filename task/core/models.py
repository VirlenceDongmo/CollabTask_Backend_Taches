from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class Project(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Task(models.Model):
    STATUS_CHOICES = [
        ('À faire', 'À faire'),
        ('En cours', 'En cours'),
        ('Terminé', 'Terminé'),
    ]

    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    difficulte = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Niveau de difficulté de 1 (facile) à 5 (très difficile)"
    )
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='À faire')
    echeance = models.DateField(null=True, blank=True)
    collaborateur_id = models.CharField(
        null=True,
        blank=True,
        help_text="ID du collaborateur provenant du service externe"
    )
    projet_id = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titre




# from django.db import models

# class Task(models.Model):
#     STATUS_CHOICES = [
#         ('À faire', 'À faire'),
#         ('En cours', 'En cours'),
#         ('Terminé', 'Terminé'),
#     ]

#     title = models.CharField(max_length=200)
#     description = models.TextField(blank=True)
#     created_by = models.IntegerField(null=True, blank=True)
#     assigned_to = models.CharField(null=True, blank=True, max_length=200)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='À faire')
#     due_date = models.DateField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(null=True, blank=True)

#     def __str__(self):
#         return self.title