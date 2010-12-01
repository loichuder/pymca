#/*##########################################################################
# Copyright (C) 2004-2010 European Synchrotron Radiation Facility
#
# This file is part of the PyMCA X-ray Fluorescence Toolkit developed at
# the ESRF by the Beamline Instrumentation Software Support (BLISS) group.
#
# This toolkit is free software; you can redistribute it and/or modify it 
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option) 
# any later version.
#
# PyMCA is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# PyMCA; if not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307, USA.
#
# PyMCA follows the dual licensing model of Trolltech's Qt and Riverbank's PyQt
# and cannot be used as a free plugin for a non-free program. 
#
# Please contact the ESRF industrial unit (industry@esrf.fr) if this license 
# is a problem for you.
#############################################################################*/
"""
Demo example of generic access to data sources.

"""
import sys
import PyMcaQt as qt
QTVERSION = qt.qVersion()

#import QSPSDataSource
#import QSpecFileDataSource
#import QEdfFileDataSource
import SpecFileDataSource
import EdfFileDataSource
import QEdfFileWidget
import os
if 0 and QTVERSION < '4.0.0':
    import MySpecFileSelector as QSpecFileWidget
    QSpecFileWidget.QSpecFileWidget = QSpecFileWidget.SpecFileSelector
else:
    import QSpecFileWidget

if (sys.platform == "win32") or (sys.platform == "darwin"):
    source_types = { SpecFileDataSource.SOURCE_TYPE: SpecFileDataSource.SpecFileDataSource,
                     EdfFileDataSource.SOURCE_TYPE:  EdfFileDataSource.EdfFileDataSource}

    source_widgets = { SpecFileDataSource.SOURCE_TYPE: QSpecFileWidget.QSpecFileWidget,
                       EdfFileDataSource.SOURCE_TYPE: QEdfFileWidget.QEdfFileWidget}
    sps = None 
else:
    #import SpsDataSource
    import QSpsDataSource
    sps = QSpsDataSource.SpsDataSource.sps
    import QSpsWidget
    source_types = { SpecFileDataSource.SOURCE_TYPE: SpecFileDataSource.SpecFileDataSource,
                     EdfFileDataSource.SOURCE_TYPE:  EdfFileDataSource.EdfFileDataSource,
                     QSpsDataSource.SOURCE_TYPE: QSpsDataSource.QSpsDataSource}

    source_widgets = { SpecFileDataSource.SOURCE_TYPE: QSpecFileWidget.QSpecFileWidget,
                       EdfFileDataSource.SOURCE_TYPE: QEdfFileWidget.QEdfFileWidget,
                       QSpsDataSource.SOURCE_TYPE: QSpsWidget.QSpsWidget}

NEXUS = True
try:
    import NexusDataSource
    import PyMcaNexusWidget
    import h5py
except:
    NEXUS = False


if NEXUS:
    source_types[NexusDataSource.SOURCE_TYPE] = NexusDataSource.NexusDataSource
    source_widgets[NexusDataSource.SOURCE_TYPE] = PyMcaNexusWidget.PyMcaNexusWidget

def getSourceType(sourceName0):
    if type(sourceName0) == type([]):
        sourceName = sourceName0[0]
    else:
        sourceName = sourceName0
    if sps is not None:
        if sourceName in sps.getspeclist():
            return QSpsDataSource.SOURCE_TYPE
    if not os.path.exists(sourceName):
        if ('%' in sourceName):
            try:
                f = h5py.File(sourceName, 'r', driver='family')
                f.close()
                f = None
                return NexusDataSource.SOURCE_TYPE
            except:
                pass        
    if os.path.exists(sourceName):
        f = open(sourceName)
        line = f.readline()
        if not len(line.replace("\n","")):
            line = f.readline()
        f.close()
        if sourceName.lower().endswith('tiff') or\
            sourceName.lower().endswith('tif'):
            mccd = False
        elif sourceName.lower().endswith('.cbf'):
            #pilatus CBF
            mccd = True
        elif len(line) < 2:
            mccd = False
        elif line[0:2] in ["II","MM"]:
            mccd = True
        else:
            mccd = False
        if (line.startswith("{")) or mccd:
            return EdfFileDataSource.SOURCE_TYPE
        else:
            if NEXUS:
                if h5py.is_hdf5(sourceName):
                    return NexusDataSource.SOURCE_TYPE
                try:
                    f = h5py.File(sourceName, 'r')
                    f.close()
                    f = None
                    return NexusDataSource.SOURCE_TYPE
                except:
                    pass                
            return SpecFileDataSource.SOURCE_TYPE
    else:
        return QSpsDataSource.SOURCE_TYPE

def QDataSource(name=None, source_type=None):
    if name is None:
        raise ValueError("Invalid Source Name")
    if source_type is None:
        source_type = getSourceType(name)    
    try:
        sourceClass = source_types[source_type]
    except KeyError:
        #ERROR invalid source type
        raise TypeError("Invalid Source Type, source type should be one of %s" % source_types.keys())
    return sourceClass(name)
  
  
if __name__ == "__main__":
    import sys,time
    try:
        sourcename=sys.argv[1]
        key       =sys.argv[2]        
    except:
        print("Usage: QDataSource <sourcename> <key>")
        sys.exit()
    #one can use this:
    #obj = EdfFileDataSource(sourcename)
    #or this:
    obj = QDataSource(sourcename)
    #data = obj.getData(key,selection={'pos':(10,10),'size':(40,40)})
    #data = obj.getData(key,selection={'pos':None,'size':None})
    data = obj.getDataObject(key)
    print("info = ",data.info)
    print("data shape = ",data.data.shape)


