from django.urls import path
from .views import *


urlpatterns =[
    path('projects/list/', ProjectListView.as_view(), name='list-projects'),
    path("task/<int:pk>/", DetailTaskView.as_view(), name='details-task'),
    path('task/create/', CreateTaskView.as_view(), name='create-task'),
    path('task/update/<int:pk>/', UpdateTaskView.as_view(), name='update-task'),
    path('task/delete/<int:pk>/', DeleteTaskView.as_view(), name='delate-task'),
    path('tasks/list/', TaskListView.as_view(), name='list-task'),
    path('task/userListTask/<int:pk>/', UserTaskListView.as_view(), name='list-user-task'),
    path('tasks/current-user/', CurrentUserTasksView.as_view(), name='current-user-task')
]