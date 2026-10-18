from django.urls import path

from .views import (
    CreateSubmissionView,
    SubmissionListView,
    SubmissionDetailView,
    DecisionView,
    HistoryView,
    SummaryView,
)
from .views import FileLinkView, LocalFileView

urlpatterns = [
    path('create/', CreateSubmissionView.as_view()),
    path('list/', SubmissionListView.as_view()),
    path('detail/<uuid:id>/', SubmissionDetailView.as_view()),
    path('decision/<uuid:id>/', DecisionView.as_view()),
    path('history/<uuid:id>/', HistoryView.as_view()),
    path('summary/', SummaryView.as_view()),
    path('file-link/<uuid:id>/', FileLinkView.as_view()),
    path('content/<uuid:id>/', LocalFileView.as_view(), name='nod-submission-content'),
]
