from django.db import models
from django.conf import settings
from django.urls import reverse


class BaseRequest(models.Model):
    STATUS_PENDING  = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES  = [
        ("pending",  "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
    ]

    from_user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    message      = models.TextField(blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class VolunteerRequest(BaseRequest):
    community       = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="volunteer_requests")
    volunteer_mode  = models.CharField(max_length=20, blank=True)   # 'offer' | 'wish'
    stay_from       = models.DateTimeField(null=True, blank=True)
    stay_to         = models.DateTimeField(null=True, blank=True)
    practice_skills       = models.CharField(max_length=500, blank=True)
    practice_skill_level  = models.CharField(max_length=20, blank=True)
    sender_skills         = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def practice_skills_list(self):
        return [s.strip() for s in self.practice_skills.split(",") if s.strip()] if self.practice_skills else []

    @property
    def sender_skills_list(self):
        return [s.strip() for s in self.sender_skills.split(",") if s.strip()] if self.sender_skills else []

    def __str__(self):
        return f"Volunteer request by {self.from_user} at {self.community} ({self.status})"

    def get_absolute_url(self):
        return reverse("matches:volunteer_detail", args=[self.pk])

    @property
    def recipient(self):
        return self.community.owner


class VolunteerRequestMessage(models.Model):
    request    = models.ForeignKey(VolunteerRequest, on_delete=models.CASCADE, related_name="messages")
    sender     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message by {self.sender} on request #{self.request_id}"
