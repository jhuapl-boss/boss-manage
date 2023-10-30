class FilesHash:
    def __init__(self, hash_alg):
        """
        Constructor.

        Args:
            hash: A hash algorithm from the hashlib standard library.
        """
        self.hash = hash_alg

    @property
    def hexdigest(self) -> str:
        """
        Returns:
            Hexidecimal hash of all given files.
        """
        return self.hash.hexdigest()

    def add_file(self, path) -> None:
        """
        Opens the given file and hashes it contents for inclusion in the
        overall hash.
        """
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.hash.update(data)
        except IsADirectoryError:
            pass
