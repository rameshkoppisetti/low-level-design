from abc import ABC, abstractmethod
from collections import deque


# =========================
# FILE SYSTEM NODES
# =========================

class FileSystemNode(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    def is_file(self):
        pass


class File(FileSystemNode):
    def __init__(self, name, size):
        super().__init__(name)
        self.size = size
        self.extension = name.split('.')[-1] if '.' in name else ""

    def is_file(self):
        return True


class Directory(FileSystemNode):
    def __init__(self, name):
        super().__init__(name)
        self.children = []

    def add(self, node: FileSystemNode):
        self.children.append(node)

    def is_file(self):
        return False


# =========================
# SPECIFICATION PATTERN
# =========================

class Specification(ABC):
    @abstractmethod
    def is_satisfied(self, file: File):
        pass

    def __and__(self, other):
        return AndSpecification(self, other)

    def __or__(self, other):
        return OrSpecification(self, other)


class ExtensionSpecification(Specification):
    def __init__(self, extension):
        self.extension = extension

    def is_satisfied(self, file: File):
        return file.extension == self.extension

class NameSpecification(Specification):
    def __init__(self, name):
        self.name = name

    def is_satisfied(self, file: File):
        return file.name == self.name

class MinSizeSpecification(Specification):
    def __init__(self, min_size):
        self.min_size = min_size

    def is_satisfied(self, file: File):
        return file.size >= self.min_size


class AndSpecification(Specification):
    def __init__(self, spec1, spec2):
        self.spec1 = spec1
        self.spec2 = spec2

    def is_satisfied(self, file: File):
        return self.spec1.is_satisfied(file) and self.spec2.is_satisfied(file)


class OrSpecification(Specification):
    def __init__(self, spec1, spec2):
        self.spec1 = spec1
        self.spec2 = spec2

    def is_satisfied(self, file: File):
        return self.spec1.is_satisfied(file) or self.spec2.is_satisfied(file)


# =========================
# FILE SEARCHER (BFS)
# =========================

class FileSearcher:

    def search(self, root: Directory, specification: Specification):
        result = []

        queue = deque([root])

        while queue:
            node = queue.popleft()

            if node.is_file():
                if specification.is_satisfied(node):
                    result.append(node.name)
            else:
                for child in node.children:
                    queue.append(child)

        return result


# =========================
# DRIVER CODE
# =========================

def main():
    # Create file system manually

    root = Directory("root")

    dir1 = Directory("documents")
    dir2 = Directory("images")

    file1 = File("resume.xml", 6 * 1024 * 1024)  # 6MB
    file2 = File("notes.txt", 500 * 1024)        # 500KB
    file3 = File("photo.jpg", 3 * 1024 * 1024)   # 3MB
    file4 = File("config.xml", 7 * 1024 * 1024)  # 1MB

    dir1.add(file1)
    dir1.add(file2)
    dir2.add(file3)
    dir2.add(file4)

    root.add(dir1)
    root.add(dir2)

    # Create search criteria
    size_spec = MinSizeSpecification(5 * 1024 * 1024)
    ext_spec = ExtensionSpecification("xml")

    combined_spec = size_spec & ext_spec

    # Search
    searcher = FileSearcher()
    result = searcher.search(root, combined_spec)
    print("Matching Files:")
    for file in result:
        print(file)
    
    spec_2 =  NameSpecification('notes.txt')
    
    result2 = searcher.search(root, spec_2)
    print("Matching Files:")
    for file in result2:
        print(file)
    
    


if __name__ == "__main__":
    main()