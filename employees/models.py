from django.db import models

class Team(models.Model):
    first_name =  models.CharField(max_length=30)
    last_name =  models.CharField(max_length=30)
    position =  models.CharField(max_length=39)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
