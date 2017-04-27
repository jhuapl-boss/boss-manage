# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil
import zipfile

def zip_directory(directory, name = "lambda"):
    target = os.path.join(tempfile.mkdtemp(), name)
    return shutil.make_archive(target, "zip", directory, directory)

def write_zip_file(full_path, zipfile_instance, arcname=None):
    """
    Writes the directory, file or symbolic link using the zipfile instance
    works with write_to_zip()
    Args:
        full_path:  full path to file, dir or symlink
        zipfile_instance: instance of a zipfile created with w or a
        arcname: Name to give the file or directory in the zip archive

    Returns:

    """
    if arcname is None:
        arcname = full_path

    if os.path.islink(full_path):
        # based on http://www.mail-archive.com/python-list@python.org/msg34223.html
        zip_info = zipfile.ZipInfo(arcname)
        zip_info.create_system = 3
        # long type of hex val of '0xA1ED0000', which is sym link attribute value
        zip_info.external_attr = 2716663808
        zipfile_instance.writestr(zip_info, os.readlink(full_path))
    else:
        zipfile_instance.write(full_path, arcname)


def write_to_zip(path, zippath, append=True, arcname=None):
    """
    will add a file, directory or symlink to a zip file.
    Args:
        path: path to file to be zipped.
        zippath: path to the zip file to be created or added to.
        append: if True write in append mode else create a new file.
        arcname: Name to give the file or directory in the zip archive

    Returns:
        None
    """
    mode = 'a' if append else 'w'
    fzip = zipfile.ZipFile(zippath, mode, zipfile.ZIP_DEFLATED)
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dst = root.replace(path, arcname)
            if '.git' in dirs:
                dirs.remove('.git')
            for d in dirs:
                dirname = os.path.join(root, d)
                dstname = os.path.join(dst, d)
                write_zip_file(dirname, fzip, dstname)
            for f in files:
                filename = os.path.join(root, f)
                dstname = os.path.join(dst, f)
                write_zip_file(filename, fzip, dstname)
    else:
        write_zip_file(path, fzip, arcname)
    fzip.close()

