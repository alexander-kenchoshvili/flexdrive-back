from django.http import JsonResponse
from .models import Project


def project_list(request):
  items = Project.objects.all()
  data = []



  

  for item in items:
        data.append({
        'id':item.id,
        'name':item.name,
        'subtitle':item.subtitle,
        'descriptioin':item.decsription,
        })
        return JsonResponse(data, safe=False)
  


# Create your views here.
