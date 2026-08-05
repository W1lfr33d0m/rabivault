import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import Facility, Organization

from .models import Document, VaultFolder

User = get_user_model()


class VaultApiTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Acme Health")
        self.other_org = Organization.objects.create(name="Other Health")

        self.facility = Facility.objects.create(organization=self.org, name="Downtown Clinic")
        self.other_facility = Facility.objects.create(organization=self.org, name="Uptown Clinic")

        self.org_admin = self._make_user(
            "org_admin_user", role="org_admin", organization=self.org, facilities=[]
        )
        self.staff = self._make_user(
            "staff_user", role="staff", organization=self.org, facilities=[self.facility]
        )

    def _make_user(self, username, *, role, organization, facilities, mfa_enabled=True):
        user = User.objects.create_user(username=username, password="pass1234")
        profile = user.profile
        profile.role = role
        profile.organization = organization
        profile.mfa_enabled = mfa_enabled
        profile.save()
        profile.facilities.set(facilities)
        return user

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["mfa_verified_user_id"] = user.id
        session.save()

    def _post_json(self, url_name, payload):
        return self.client.post(
            reverse(f"vault:{url_name}"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _make_folder(self, name, *, parent=None, facility=None, organization=None):
        return VaultFolder.objects.create(
            organization=organization or self.org,
            facility=facility,
            parent=parent,
            name=name,
        )

    def _make_document(self, title, *, folder=None, facility=None, organization=None, status="active"):
        return Document.objects.create(
            organization=organization or self.org,
            facility=facility,
            folder=folder,
            title=title,
            file="documents/sample.pdf",
            status=status,
        )


class FolderMoveTests(VaultApiTestCase):
    def test_staff_without_manage_role_is_denied(self):
        root = self._make_folder("Root", facility=self.facility)
        target = self._make_folder("Target", facility=self.facility)

        self._login(self.staff)
        response = self._post_json("api_folder_move", {"folder_id": root.id, "new_parent_id": target.id})

        self.assertEqual(response.status_code, 403)

    def test_cannot_move_folder_into_its_own_descendant(self):
        parent = self._make_folder("Parent", facility=self.facility)
        child = self._make_folder("Child", parent=parent, facility=self.facility)

        self._login(self.org_admin)
        response = self._post_json("api_folder_move", {"folder_id": parent.id, "new_parent_id": child.id})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "cycle")

    def test_cannot_move_into_folder_with_different_facility(self):
        folder = self._make_folder("Folder", facility=self.facility)
        target = self._make_folder("Target", facility=self.other_facility)

        self._login(self.org_admin)
        response = self._post_json("api_folder_move", {"folder_id": folder.id, "new_parent_id": target.id})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "facility_mismatch")

    def test_successful_move(self):
        folder = self._make_folder("Folder", facility=self.facility)
        target = self._make_folder("Target", facility=self.facility)

        self._login(self.org_admin)
        response = self._post_json("api_folder_move", {"folder_id": folder.id, "new_parent_id": target.id})

        self.assertEqual(response.status_code, 200)
        folder.refresh_from_db()
        self.assertEqual(folder.parent_id, target.id)


class FolderDeleteTests(VaultApiTestCase):
    def test_delete_blocked_when_subfolder_present(self):
        parent = self._make_folder("Parent", facility=self.facility)
        self._make_folder("Child", parent=parent, facility=self.facility)

        self._login(self.org_admin)
        response = self._post_json("api_folder_delete", {"folder_id": parent.id})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "not_empty")
        self.assertTrue(VaultFolder.objects.filter(id=parent.id).exists())

    def test_delete_blocked_when_active_document_present(self):
        folder = self._make_folder("Folder", facility=self.facility)
        self._make_document("Report", folder=folder, facility=self.facility)

        self._login(self.org_admin)
        response = self._post_json("api_folder_delete", {"folder_id": folder.id})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "not_empty")

    def test_delete_succeeds_when_empty(self):
        folder = self._make_folder("Folder", facility=self.facility)

        self._login(self.org_admin)
        response = self._post_json("api_folder_delete", {"folder_id": folder.id})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(VaultFolder.objects.filter(id=folder.id).exists())


class DocumentMoveTests(VaultApiTestCase):
    def test_cannot_move_into_folder_with_different_facility(self):
        document = self._make_document("Report", facility=self.facility)
        target = self._make_folder("Target", facility=self.other_facility)

        self._login(self.org_admin)
        response = self._post_json(
            "api_document_move", {"public_id": str(document.public_id), "folder_id": target.id}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "facility_mismatch")

    def test_successful_move(self):
        document = self._make_document("Report", facility=self.facility)
        target = self._make_folder("Target", facility=self.facility)

        self._login(self.org_admin)
        response = self._post_json(
            "api_document_move", {"public_id": str(document.public_id), "folder_id": target.id}
        )

        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.folder_id, target.id)

    def test_staff_outside_facility_scope_is_denied(self):
        document = self._make_document("Report", facility=self.other_facility)
        target = self._make_folder("Target", facility=self.other_facility)

        self._login(self.staff)
        response = self._post_json(
            "api_document_move", {"public_id": str(document.public_id), "folder_id": target.id}
        )

        self.assertEqual(response.status_code, 403)


class FolderContentsTests(VaultApiTestCase):
    def test_contents_lists_children_and_documents(self):
        folder = self._make_folder("Folder", facility=self.facility)
        self._make_folder("Child", parent=folder, facility=self.facility)
        self._make_document("Report", folder=folder, facility=self.facility)

        self._login(self.org_admin)
        response = self.client.get(reverse("vault:api_folder_contents"), {"folder": folder.id})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["folders"]), 1)
        self.assertEqual(len(data["documents"]), 1)
        self.assertFalse(data["can_delete_folder"])

    def test_can_delete_folder_true_when_empty(self):
        folder = self._make_folder("Empty", facility=self.facility)

        self._login(self.org_admin)
        response = self.client.get(reverse("vault:api_folder_contents"), {"folder": folder.id})

        self.assertTrue(response.json()["can_delete_folder"])

    def test_unverified_mfa_session_redirects_instead_of_returning_json(self):
        folder = self._make_folder("Folder", facility=self.facility)

        self.client.force_login(self.org_admin)
        response = self._post_json("api_folder_delete", {"folder_id": folder.id})

        self.assertEqual(response.status_code, 302)
