from django.urls import path

from .views import CreateUploadView, CompleteUploadView, UploadStatusView, LocalUploadView

urlpatterns = [
    path('create/', CreateUploadView.as_view()),
    path('complete/<uuid:id>/', CompleteUploadView.as_view()),
    path('status/<uuid:id>/', UploadStatusView.as_view()),
    path('content/<uuid:id>/', LocalUploadView.as_view(), name='nod-local-upload'),
]
