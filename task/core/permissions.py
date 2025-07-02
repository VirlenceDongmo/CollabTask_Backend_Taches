from rest_framework import permissions


class IsStaffPermission(permissions.DjangoModelPermissions):


    def has_permissin(self,request,view):
        if request.user.is_staff:
            return False
        return super.has_permission(request,view)

    perm_map = {
        'GET':['%(app_label)s.view_%(model_name)s'],
        'OPTIONS':[],
        'HEAD':[],
        'POST':['%(app_label)s.view_%(model_name)s'],
        'PUT':['%(app_label)s.view_%(model_name)s'],
        'PATCH':['%(app_label)s.view_%(model_name)s'],
        'DELETE':['%(app_label)s.view_%(model_name)s'],
    }

    # def has_permission(self, request, view):
    #     user = request.user
    #     if user.is_staff:
    #         if user.has_Perm('core.add_task') :
    #             return True 
    #         if user.has_Perm('core.change_task') :
    #             return True 
    #         if user.has_Perm('core.delete_task') :
    #             return True 
    #         if user.has_Perm('core.view_task') :
    #             return True 
    #     return False