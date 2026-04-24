from enum import Enum
import uuid
import datetime


class FileVersion:
    def __init__(self, file_id, content, version_id):
        self.version_id = version_id
        self.file_id = file_id
        self.content = content
        self.timestamp = datetime.datetime.now()

    def __str__(self):
        return f"{self.file_id} : version : {self.version_id}"


class File:
    def __init__(self, name, created_by):
        self.id = uuid.uuid4()
        self.name = name
        self.created_by = created_by
        self.created_at = datetime.datetime.now()
        self.versions = []
        self.current_version = None

    def add_version(self, content):
        version_id = len(self.versions)
        version = FileVersion(self.id, content, version_id)

        self.versions.append(version)
        self.current_version = version

    def get_latest_content(self):
        return self.current_version.content if self.current_version else None

    def __str__(self):
        return f"id : {self.id} : name : {self.name}"


class User:
    def __init__(self, name):
        self.id = uuid.uuid4()
        self.name = name
        
class PermissionType(Enum):
    READ=1
    WRITE=2
    OWNER=3
    
class Permission:
    def __init__(self, user_id, file_id, access_type):
        self.user_id=user_id
        self.file_id=file_id
        self.access_type= access_type
        


class FileService:  
    def __init__(self):
        self.permissions={}
        self.files={} # user id -> 
    
    def create_file(self, user: User, name: str, content: str):
        file= File(name, user.id)
        file.add_version(content)
        # add it 
        perm = Permission(user.id, file.id, access_type= PermissionType.OWNER)
        self.permissions[(user.id,file.id)]= perm
        self.files[file.id] = file
        return file
        
        
    def upload_version(self, user, file_id, content):
        file = self.files.get(file_id)
        if not file:
            raise ValueError("File not found")

        perm = self.permissions.get((user.id, file_id))
        if not perm:
            raise ValueError("Access denied")

        self.access_control_check(perm, PermissionType.WRITE)

        file.add_version(content)
    
    def download(self, user, file_id):
        file = self.files.get(file_id)
        if not file:
            raise ValueError("File not found")

        perm = self.permissions.get((user.id, file_id))
        if not perm:
            raise ValueError("Access denied")

        self.access_control_check(perm, PermissionType.READ)

        return file.get_latest_content()
    
    def share(self, user: User, file_id: str, target_user: User, access: PermissionType):
        perm = self.permissions.get((user.id, file_id))
        if not perm:
            raise ValueError("Access Denied")

        # Only OWNER can share
        if perm.access_type != PermissionType.OWNER:
            raise Exception("Only owner can share")

        self.permissions[(target_user.id, file_id)] = Permission(
            target_user.id, file_id, access
        )
            
    
    def access_control_check(self, perm, required):
        if perm.access_type == PermissionType.OWNER:
            return

        if required == PermissionType.READ and perm.access_type in [
            PermissionType.READ,
            PermissionType.WRITE,
        ]:
            return

        if required == PermissionType.WRITE and perm.access_type == PermissionType.WRITE:
            return

        raise Exception("Invalid Access")
    

def main():
    u = User("satya")
    fs = FileService()
    f= fs.create_file(u, "satya.txt", "helllo my world")
    downloaded_file=fs.download(u,f.id)
    print(downloaded_file)
    fs.download(u,f.id)
    fs.upload_version(u,f.id,"helllooooo")
    downloaded_file= fs.download(u,f.id)
    print(downloaded_file)
    


if __name__ == "__main__":
    main()