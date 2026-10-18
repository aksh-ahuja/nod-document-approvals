from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReviewerAccessMigrationTests(TransactionTestCase):
    def test_existing_active_verified_users_receive_reviewer_access(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()

        try:
            previous = [('nod_auth_service', '0001_initial')]
            executor.migrate(previous)
            User = executor.loader.project_state(previous).apps.get_model(
                'nod_auth_service', 'User'
            )
            active = User.objects.create(email='active@example.com', email_verified=True)
            unverified = User.objects.create(email='unverified@example.com')
            inactive = User.objects.create(
                email='inactive@example.com', email_verified=True, is_active=False
            )
            reviewer = User.objects.create(
                email='reviewer@example.com', email_verified=True, can_review=True
            )

            target = [('nod_auth_service', '0002_default_reviewer_access')]
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            User = executor.loader.project_state(target).apps.get_model('nod_auth_service', 'User')

            self.assertTrue(User.objects.get(pk=active.pk).can_review)
            self.assertTrue(User.objects.get(pk=reviewer.pk).can_review)
            self.assertFalse(User.objects.get(pk=unverified.pk).can_review)
            self.assertFalse(User.objects.get(pk=inactive.pk).can_review)
            self.assertTrue(User.objects.create(email='new@example.com').can_review)
        finally:
            MigrationExecutor(connection).migrate(latest)
