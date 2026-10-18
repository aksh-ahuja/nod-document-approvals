import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from nod_auth_service.services import GenericAuthService

from ..models import Submission, SubmissionEvent
from .generic_submission_service import GenericSubmissionService


class GenericDemoService:

    @classmethod
    @transaction.atomic
    def seed(cls):
        if not settings.NOD_ENABLE_DEMO:
            raise ValueError('Enable NOD_ENABLE_DEMO in local development to seed demo data.')

        users = GenericAuthService.seed_demo_users()
        jamie, alex, sam = users
        documents = [
            (
                'Q4 brand direction',
                'pending',
                alex,
                (
                    'A clearer direction for the next chapter.\n'
                    '\n'
                    'THE IDEA\n'
                    'Make every touchpoint feel useful, thoughtful, and unmistakably us. The Q4 '
                    'direction brings a warmer palette, sharper messaging, and a more consistent '
                    'visual language.\n'
                    '\n'
                    'WHAT IS CHANGING\n'
                    '• A refined identity across the website and product.\n'
                    '• A simplified messaging framework for launch campaigns.\n'
                    '• A reusable toolkit for the design and marketing teams.\n'
                    '\n'
                    'SCOPE & TIMELINE\n'
                    'Week 1: finalise the direction and creative principles.\n'
                    'Week 2: develop the launch assets and key templates.\n'
                    'Week 3: review, refine, and hand over.\n'
                    '\n'
                    'DECISION NEEDED\n'
                    'Please review the direction and confirm we can move into production.'
                ),
            ),
            (
                'October campaign proposal',
                'pending',
                sam,
                (
                    'Launch a three-week campaign introducing our new product experience.\n'
                    '\n'
                    'Audience: small creative and operations teams.\n'
                    'Channels: email, product updates, and organic social.\n'
                    'Budget: ₹45,000.\n'
                    '\n'
                    'Please approve the proposed scope before we begin production.'
                ),
            ),
            (
                'Customer onboarding playbook',
                'approved',
                alex,
                (
                    'A practical guide for a better first week.\n'
                    '\n'
                    'Day 1: welcome and workspace setup.\n'
                    'Day 2: first submission and reviewer assignment.\n'
                    'Day 3: feedback and follow-up.\n'
                    '\n'
                    'Success means every new team has completed one review cycle.'
                ),
            ),
            (
                'Website copy refresh',
                'rejected',
                sam,
                (
                    'Proposed homepage message: Move work forward with clearer decisions.\n'
                    '\n'
                    'Update the hero, feature descriptions, and onboarding copy to match our new '
                    'positioning.'
                ),
            ),
            (
                'Partner launch checklist',
                'approved',
                sam,
                (
                    'Confirm assets, timelines, owners, and the launch communication plan before '
                    'partner onboarding begins.'
                ),
            ),
            (
                'Design system handoff',
                'pending',
                alex,
                (
                    'Shared tokens, accessible components, and usage guidelines for the product '
                    'team.\n'
                    '\n'
                    'Please review button states, form validation, and the mobile navigation '
                    'behaviour.'
                ),
            ),
        ]

        for index, (title, status, reviewer, content) in enumerate(documents):
            key = uuid.uuid5(uuid.NAMESPACE_DNS, f'nod-demo-{index}')

            if Submission.objects.filter(submitter=jamie, client_request_id=key).exists():
                continue

            result = GenericSubmissionService.create_submission(
                jamie, title, content, reviewer.public_id, key
            )
            submission = result.data
            when = timezone.now() - timedelta(days=index + 1, hours=2)
            Submission.objects.filter(pk=submission.pk).update(created_at=when)
            SubmissionEvent.objects.filter(submission=submission).update(created_at=when)

            if status != 'pending':
                note = (
                    'Looks good. Ready to move forward.'
                    if status == 'approved'
                    else 'Please add the final headlines and a clearer primary call to action.'
                )
                GenericSubmissionService.decide(reviewer, submission.public_id, status, note)

        return users
