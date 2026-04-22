from django.http import JsonResponse
from .models import Team

def team_list(request):
    items = Team.objects.all()
    data = []
    
    for item in items:
        data.append({
            'id': item.id,
            'first_name':item.first_name,
            'last_name': item.last_name,
            'position': item.position,
        })
    return JsonResponse(data, safe=False)

# Create your views here.
