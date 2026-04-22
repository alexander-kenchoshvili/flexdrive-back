from django.db import models

class Project(models.Model):
    name =  models.CharField(max_length=15)
    subtitle = models.CharField(max_length=100)
    decsription = models.CharField(max_length=1000)

    def __str__(self):
        return self.name



# Create your models here.
