import os
import shutil
import struct
import sys
import traceback

import wx
import wx.lib.mixins.listctrl as listmix

import id3reader
import mp4tag

ROOT = 'f:/iPod_Control/Music'

def get_id3tag(fn):
    id3 = id3reader.Reader(fn)
    rv = {}
    def add(t, s, m=lambda x: x):
        v = id3.getValue(s)
        if v is not None:
            rv[t] = m(v)
            
    add('Artist', 'artist')
    add('Album',  'album')
    add('Track',  'track', lambda x: int(x.split('/')[0]))
    add('Title',  'title')
    if rv == {}:
        id3.dump()
        raise ValueError
    return rv


get_mp4tag = mp4tag.M4ATags

file_handlers = {
    '.m4a': get_mp4tag,
    '.m4v': get_mp4tag,
    '.m4p': get_mp4tag,
    '.mp3': get_id3tag }

def get_extension(fn):
    return os.path.splitext(fn)[1]

def has_supported_extension(fn):
    return file_handlers.has_key(get_extension(fn))

def get_tags(fn):
    return file_handlers[get_extension(fn)](fn)

def make_safe_fn(fn):
    if not isinstance(fn, basestring):
        return fn
    
    bad_chars = '|?*:<>"/\\'
    for b in bad_chars:
        fn = fn.replace(b, '_')
    return fn

def get_safe_tags(fn):
    tags = get_tags(fn)
    return dict([(k, make_safe_fn(v)) for k, v in tags.items()])

def make_target_path(fn, tags):
    ext = get_extension(fn)
    
    target = ''
    if tags.has_key('Artist'):
        target += '%(Artist)s/'
    if tags.has_key('Album'):
        target += '%(Album)s/'
    if tags.has_key('Track'):
        target += '%(Track)02d - '
    target += '%(Title)s'
    try:
        return (target % tags) + ext
    except KeyError:
        return os.path.basename(fn) + ext


class AutoWidthListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
    def __init__(self, *args, **kw):
        wx.ListCtrl.__init__(self, *args, **kw)
        listmix.ListCtrlAutoWidthMixin.__init__(self)


ID_SET_SOURCE      = 1000
ID_SET_DESTINATION = 1001
ID_EXTRACT         = 1002

class MainPanel(wx.Panel):
    def __init__(self, parent):
        super(MainPanel, self).__init__(parent, -1)

        self.__sourceFolder      = None
        self.__destinationFolder = None
        self.__copyPlan = {}

        self.__createContents()
        self.__updateListView()
        self.__updateSourceFolder()
        self.__updateDestinationFolder()

    def __createContents(self):
        list_style = wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES

        self.__list = AutoWidthListCtrl(self, -1, style=list_style)
        self.__list.InsertColumn(0, 'Original')
        self.__list.InsertColumn(1, 'Destination')

        self.__sourceFolderControl      = wx.StaticText(self, -1, 'Source Folder:')
        self.__destinationFolderControl = wx.StaticText(self, -1, 'Destination Folder:')

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        def add_button(id, fn, name):
            button_sizer.Add(wx.Button(self, id, name))
            wx.EVT_BUTTON(self, id, fn)
        add_button(ID_SET_SOURCE,      self.onSetSourceFolder,      'Set iPod Drive')
        add_button(ID_SET_DESTINATION, self.onSetDestinationFolder, 'Set Destination Folder')
        add_button(ID_EXTRACT,         self.onExtract,              'Extract!')

        self.__panel = wx.BoxSizer(wx.VERTICAL)
        self.__panel.Add(self.__list, 1, wx.EXPAND)
        self.__panel.Add(self.__sourceFolderControl,      flag=wx.ALIGN_CENTER, border=10)
        self.__panel.Add(self.__destinationFolderControl, flag=wx.ALIGN_CENTER, border=10)
        self.__panel.Add(button_sizer)

        self.SetSizer(self.__panel)
        self.__panel.SetSizeHints(self)

    def __updateListView(self):
        self.__list.DeleteAllItems()
        
        for key, value in sorted(self.__makeCompleteCopyPlan().items()):
            idx = self.__list.InsertStringItem(sys.maxint, key)

            if self.__destinationFolder is not None:
                destination_value = os.path.join(self.__destinationFolder, value)
            else:
                destination_value = 'No destination folder!'
            self.__list.SetStringItem(idx, 1, destination_value)

    def __updateSourceFolder(self):
        if self.__sourceFolder is None:
            v = 'Not set!'
        else:
            v = self.__sourceFolder
        self.__sourceFolderControl.SetLabel('Source Folder: %s' % v)
        self.__panel.Layout()

    def __updateDestinationFolder(self):
        if self.__destinationFolder is None:
            v = 'Not set!'
        else:
            v = self.__destinationFolder
        self.__destinationFolderControl.SetLabel('Destination Folder: %s' % v)
        self.__panel.Layout()

    def __makeCompleteCopyPlan(self):
        if self.__destinationFolder is None:
            return dict([(key, None) for key in self.__copyPlan.keys()])
        
        rv = {}
        for k, v in self.__copyPlan.items():
            rv[k] = os.path.join(self.__destinationFolder, v)
        return rv

    def __getFolder(self, title):
        dlg = wx.DirDialog(self, title, style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.GetPath()
        else:
            return None

    def onSetSourceFolder(self, event):
        path = self.__getFolder('Select iPod Drive')
        if path is None:
            return

        MAXIMUM = 200

        style = wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME 
        dlg = wx.ProgressDialog('Searching for files...', 'Searching for files...', maximum=MAXIMUM, parent=self, style=style)
        all_files = []
        try:
            i = 0
            for dir, subdirs, files in os.walk(path):
                for f in files:
                    fn = os.path.join(dir, f)
                    if has_supported_extension(fn):
                        all_files.append(fn)
                        i = (i + 1) % MAXIMUM
                        if not dlg.Update(i, newmsg='Found %s' % fn):
                            return

        finally:
            dlg.Destroy()

        copy_plan = {}

        style = wx.PD_CAN_ABORT | wx.PD_ESTIMATED_TIME | wx.PD_REMAINING_TIME
        dlg = wx.ProgressDialog('Analyzing files...', 'Analyzing files...', maximum=len(all_files), parent=self, style=style)
        try:
            for i, fn in enumerate(all_files):
                if not dlg.Update(i, newmsg='Analyzing %s' % fn):
                    return
                tags = get_safe_tags(fn)
                copy_plan[fn] = make_target_path(fn, tags)
        finally:
            dlg.Destroy()

        # Update the list with destinations.
        self.__sourceFolder = path
        self.__copyPlan = copy_plan
        self.__updateSourceFolder()
        self.__updateListView()
        

    def onSetDestinationFolder(self, event):
        path = self.__getFolder('Select Destination Folder')
        if path is None:
            return

        self.__destinationFolder = path
        self.__updateDestinationFolder()
        self.__updateListView()

    def onExtract(self, event):
        def showDialog(text, style=wx.OK|wx.ICON_ERROR):
            return wx.MessageDialog(self, text, 'Extract', style).ShowModal()

        # You need at least a source folder and a destination folder.
        if self.__sourceFolder is None:
            showErrorDialog('You must set your iPod drive before extracting.')
            return
        if self.__destinationFolder is None:
            showErrorDialog('You must set the destination folder before extracting.')
            return

        completeCopyPlan = self.__makeCompleteCopyPlan()
        if len(completeCopyPlan) == 0:
            showErrorDialog('There are no files to extract!')
            return

        def printable(s):
            return s.encode('ascii', 'backslashreplace')

        def makeDirectoryIfNeeded(dirname):
            if os.path.exists(dirname):
                return
            try:
                os.makedirs(dirname)
            except:
                traceback.print_exc()
                print >> sys.stderr, 'Failed to make directory:', printable(os.path.dirname(target))

        style = wx.PD_CAN_ABORT | wx.PD_ESTIMATED_TIME | wx.PD_REMAINING_TIME
        dlg = wx.ProgressDialog('Extracting files...', 'Extracting files...', maximum=len(completeCopyPlan), parent=self, style=style)
        try:
            for i, (source, target) in enumerate(sorted(completeCopyPlan.items())):
                if not dlg.Update(i, newmsg='Extracting %s' % os.path.basename(target)):
                    return

                makeDirectoryIfNeeded(os.path.dirname(target))
                    
                try:
                    shutil.copy2(source, target)
                except:
                    traceback.print_exc()
                    print >> sys.stderr, 'Failed to copy %s -> %s' % (printable(source), printable(target))
        finally:
            dlg.Destroy()

        showDialog('Extraction of %s files complete!' % len(completeCopyPlan), wx.OK)
    
class MainFrame(wx.Frame):
    def __init__(self):
        super(MainFrame, self).__init__(None, wx.ID_ANY, 'iPodExtract')
        MainPanel(self)


if __name__ == '__main__':
    app = wx.PySimpleApp()
    frame = MainFrame()
    frame.Show(1)
    app.MainLoop()
