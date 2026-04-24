import uuid
import datetime
from enum import Enum


# =========================
# ENUMS
# =========================

class PermissionType(Enum):
    READ = 1
    WRITE = 2
    OWNER = 3


# =========================
# BASE NODE (COMPOSITE)
# =========================

class Node:
    def __init__(self, name, owner_id):
        self.id = uuid.uuid4()
        self.name = name
        self.owner_id = owner_id
        self.created_at = datetime.datetime.now()


# =========================
# FILE (LEAF)
# =========================

class FileVersion:
    def __init__(self, file_id, content, version_id):
        self.version_id = version_id
        self.file_id = file_id
        self.content = content
        self.timestamp = datetime.datetime.now()


class File(Node):
    def __init__(self, name, owner_id):
        super().__init__(name, owner_id)
        self.versions = []
        self.current_version = None

    def add_version(self, content):
        version_id = len(self.versions)
        version = FileVersion(self.id, content, version_id)

        self.versions.append(version)
        self.current_version = version

    def get_content(self):
        return self.current_version.content if self.current_version else None


# =========================
# FOLDER (COMPOSITE)
# =========================

class Folder(Node):
    def __init__(self, name, owner_id):
        super().__init__(name, owner_id)
        self.children = {}  # name → Node

    def add(self, node):
        self.children[node.name] = node

    def get(self, name):
        return self.children.get(name)


# =========================
# PERMISSION
# =========================

class Permission:
    def __init__(self, user_id, node_id, access_type):
        self.user_id = user_id
        self.node_id = node_id
        self.access_type = access_type


# =========================
# USER
# =========================

class User:
    def __init__(self, name):
        self.id = uuid.uuid4()
        self.name = name


# =========================
# FILE SYSTEM SERVICE
# =========================

class FileSystemService:
    def __init__(self):
        self.root = Folder("root", "system")
        self.permissions = {}

    # ---------- PERMISSION ----------
    def _check_access(self, perm, required):
        if perm.access_type == PermissionType.OWNER:
            return

        if required == PermissionType.READ and perm.access_type in [
            PermissionType.READ,
            PermissionType.WRITE,
        ]:
            return

        if required == PermissionType.WRITE and perm.access_type == PermissionType.WRITE:
            return

        raise Exception("Access denied")

    def _get_permission(self, user_id, node_id):
        return self.permissions.get((user_id, node_id))
    
    def root_permission(self, user):
        self.permissions[(user.id, self.root.id)] = Permission(
            user.id, self.root.id, PermissionType.OWNER
        )

    # ---------- NAVIGATION ----------
    def _traverse(self, path):
        node = self.root
        for p in path:
            if not isinstance(node, Folder):
                raise Exception("Invalid path")
            node = node.get(p)
            if not node:
                raise Exception("Path not found")
        return node

    # ---------- CREATE ----------
    def create_folder(self, user, path, folder_name):
        parent = self._traverse(path)

        perm = self._get_permission(user.id, parent.id)
        self._check_access(perm, PermissionType.WRITE)

        folder = Folder(folder_name, user.id)
        parent.add(folder)

        self.permissions[(user.id, folder.id)] = Permission(
            user.id, folder.id, PermissionType.OWNER
        )

    def create_file(self, user, path, name, content):
        parent = self._traverse(path)

        perm = self._get_permission(user.id, parent.id)
        self._check_access(perm, PermissionType.WRITE)

        file = File(name, user.id)
        file.add_version(content)

        parent.add(file)

        self.permissions[(user.id, file.id)] = Permission(
            user.id, file.id, PermissionType.OWNER
        )

    # ---------- OPERATIONS ----------
    def upload(self, user, path, content):
        file = self._traverse(path)

        perm = self._get_permission(user.id, file.id)
        self._check_access(perm, PermissionType.WRITE)

        file.add_version(content)

    def download(self, user, path):
        file = self._traverse(path)

        perm = self._get_permission(user.id, file.id)
        self._check_access(perm, PermissionType.READ)

        return file.get_content()

    def share(self, owner, path, target_user, access):
        node = self._traverse(path)

        perm = self._get_permission(owner.id, node.id)
        if perm.access_type != PermissionType.OWNER:
            raise Exception("Only owner can share")

        self.permissions[(target_user.id, node.id)] = Permission(
            target_user.id, node.id, access
        )


# =========================
# DEMO
# =========================

def main():
    fs = FileSystemService()

    user1 = User("Satya")
    user2 = User("Rahul")

    # root permission
    fs.root_permission(user1)

    # create folder
    fs.create_folder(user1, [], "docs")

    # create file
    fs.create_file(user1, ["docs"], "resume.txt", "v1")

    # upload new version
    fs.upload(user1, ["docs", "resume.txt"], "v2")

    # share
    fs.share(user1, ["docs", "resume.txt"], user2, PermissionType.READ)

    # download
    content = fs.download(user2, ["docs", "resume.txt"])
    print(content)


if __name__ == "__main__":
    main()