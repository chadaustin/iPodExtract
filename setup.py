


import os, sys
import glob

from distutils.core import setup
import py2exe

setup(
    name="Extract iPod",
    windows = [{"script" : "iPodExtract.py"}],
    data_files=['iPodExtract.exe.manifest'],
    options = {"py2exe":
               { "excludes": ["doctest", "_tkinter"],
                 "dll_excludes": ["opengl32.dll", "ddraw.dll", "MFC42.dll", "COMCTL32.dll", "tk84.dll", "tcl84.dll", "d3d8.dll", "d3d8thk.dll"],
                 }
               }
    )
