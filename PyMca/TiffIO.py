__author__ = "V.A. Sole - ESRF Data Analysis"

import sys
import os
import struct
import string
import numpy
#import time

DEBUG = 0
ALLOW_MULTIPLE_STRIPS = False

TAG_ID  = { 256:"NumberOfColumns",           # S or L ImageWidth
            257:"NumberOfRows",              # S or L ImageHeight
            258:"BitsPerSample",             # S Number of bits per component
            259:"Compression",               # SHORT (1 - NoCompression, ... 
            262:"PhotometricInterpretation", # SHORT (0 - WhiteIsZero, 1 -BlackIsZero, 2 - RGB, 3 - Palette color
            270:"ImageDescription",          # ASCII
            273:"StripOffsets",              # S or L, for each strip, the byte offset of the strip
            278:"RowsPerStrip",              # S or L, number of rows in each back may be not for the last
            279:"StripByteCounts",           # S or L, The number of bytes in the strip AFTER any compression
            305:"Software",                  # ASCII
            306:"Date",                      # ASCII
            339:"SampleFormat",              # SHORT Interpretation of data in each pixel
            }

#TILES ARE TO BE SUPPORTED TOO ...
TAG_NUMBER_OF_COLUMNS  = 256
TAG_NUMBER_OF_ROWS     = 257
TAG_BITS_PER_SAMPLE    = 258
TAG_PHOTOMETRIC_INTERPRETATION = 262
TAG_COMPRESSION        = 259
TAG_IMAGE_DESCRIPTION  = 270
TAG_STRIP_OFFSETS      = 273
TAG_ROWS_PER_STRIP     = 278
TAG_STRIP_BYTE_COUNTS  = 279
TAG_SOFTWARE           = 305
TAG_DATE               = 306
TAG_SAMPLE_FORMAT      = 339   

FIELD_TYPE  = {1:('BYTE', "B"),
               2:('ASCII', "s"), #string ending with binary zero
               3:('SHORT', "H"),
               4:('LONG', "I"),
               5:('RATIONAL',"II"),
               6:('SBYTE', "b"),
               7:('UNDEFINED',"B"),
               8:('SSHORT', "h"),
               9:('SLONG', "i"),
               10:('SRATIONAL',"ii"),
               11:('FLOAT', "f"),
               12:('DOUBLE', "d")}

FIELD_TYPE_OUT = { 'B':   1,
                   's':   2,
                   'H':   3,
                   'I':   4,
                   'II':  5,
                   'b':   6,
                   'h':   8,
                   'i':   9,
                   'ii': 10,
                   'f':  11,
                   'd':  12}

#sample formats (http://www.awaresystems.be/imaging/tiff/tiffflags/sampleformat.html)
SAMPLE_FORMAT_UINT          = 1
SAMPLE_FORMAT_INT           = 2
SAMPLE_FORMAT_FLOAT         = 3   #floating point
SAMPLE_FORMAT_VOID          = 4   #undefined data, usually assumed UINT
SAMPLE_FORMAT_COMPLEXINT    = 5
SAMPLE_FORMAT_COMPLEXIEEEFP = 6



class TiffIO:
    def __init__(self, filename, mode=None, cache_length=20):
        if mode is None:
            mode = 'rb'
        if 'b' not in mode:
            mode = mode + 'b'
        if 'a' in mode.lower():
            raise IOError("Mode %s makes no sense on TIFF files. Consider 'rb+'" % mode)
        if ('w' in mode):
            if '+' not in mode:
                mode += '+'
        #if isinstance(filename, file): #does not work in python 3
        if hasattr(filename, "seek"):
            fd = filename
            self._access = None
        else:
            #the b is needed for windows and python 3
            fd = open(filename, mode)
            self._access = mode

        self._initInternalVariables(fd)            
        self._maxImageCacheLength = cache_length

    def _initInternalVariables(self, fd=None):
        if fd is None:
            fd = self.fd
        else:
            self.fd = fd
        # read the order
        fd.seek(0)
        order = fd.read(2).decode()
        if len(order):
            if order == "II":
                #intel, little endian
                fileOrder = "little"
                self._structChar = '<'
            elif order == "MM":
                #motorola, high endian
                fileOrder = "big"
                self._structChar = '>'
            else:
                raise IOError("File is not a Mar CCD file, nor a TIFF file")
            a = fd.read(2)
            fortyTwo = struct.unpack(self._structChar+"H",a)[0]
            if fortyTwo != 42:
                raise IOError("Invalid TIFF version %d" % fortyTwo)
            else:
                if DEBUG:
                    print("VALID TIFF VERSION")
            if sys.byteorder != fileOrder:
                swap = True
            else:
                swap = False
        else:
            if sys.byteorder == "little":
                self._structChar = '<'
            else:
                self._structChar = '>'
            swap = False
        self._swap = swap
        self._IFD = []
        self._imageDataCacheIndex = []
        self._imageDataCache  = []
        self._imageInfoCacheIndex  = []
        self._imageInfoCache  = []
        self.getImageFileDirectories(fd)

    def __makeSureFileIsOpen(self):
        if not self.fd.closed:
            return
        if DEBUG:
            print("Reopening closed file")
        fileName = self.fd.name
        if self._access is None:
            #we do not own the file
            #open in read mode
            newFile = open(fileName,'rb')
        else:
            newFile = open(fileName, self._access)
        self.fd  = newFile

    def __makeSureFileIsClosed(self):
        if self._access is None:
            #we do not own the file
            if DEBUG:
                print("Not closing not owned file")
            return
        
        if not self.fd.closed:
            self.fd.close()

    def getNumberOfImages(self):
        #update for the case someone has done anything?
        self._updateIFD()
        return len(self._IFD)

    def _updateIFD(self):
        self.__makeSureFileIsOpen()
        self.getImageFileDirectories()
        self.__makeSureFileIsClosed()
                
    def getImageFileDirectories(self, fd=None):
        if fd is None:
            fd = self.fd
        else:
            self.fd = fd
        st = self._structChar
        fd.seek(4)
        self._IFD = []
        nImages = 0
        fmt = st + 'I'
        inStr = fd.read(struct.calcsize(fmt))
        if not len(inStr):
            offsetToIFD = 0
        else:
            offsetToIFD = struct.unpack(fmt, inStr)[0]
        if DEBUG:
            print("Offset to first IFD = %d" % offsetToIFD)
        while offsetToIFD != 0:
            self._IFD.append(offsetToIFD)
            nImages += 1
            fd.seek(offsetToIFD)
            fmt = st + 'H'
            numberOfDirectoryEntries = struct.unpack(fmt,fd.read(struct.calcsize(fmt)))[0]
            if DEBUG:
                print("Number of directory entries = %d" % numberOfDirectoryEntries)

            fmt = st + 'I'
            fd.seek(offsetToIFD + 2 + 12 * numberOfDirectoryEntries)
            offsetToIFD = struct.unpack(fmt,fd.read(struct.calcsize(fmt)))[0]
            if DEBUG:
                print("Next Offset to IFD = %d" % offsetToIFD)
            #offsetToIFD = 0 
        if DEBUG:
            print("Number of images found = %d" % nImages)
        return nImages

    def _parseImageFileDirectory(self, nImage):
        offsetToIFD = self._IFD[nImage]
        st = self._structChar
        fd = self.fd
        fd.seek(offsetToIFD)
        fmt = st + 'H'
        numberOfDirectoryEntries = struct.unpack(fmt,fd.read(struct.calcsize(fmt)))[0]
        if DEBUG:
            print("Number of directory entries = %d" % numberOfDirectoryEntries)

        fmt = st + 'HHI4s'
        tagIDList = []
        fieldTypeList = []
        nValuesList = []
        valueOffsetList = []
        for i in range(numberOfDirectoryEntries):
            tagID, fieldType, nValues, valueOffset = struct.unpack(fmt, fd.read(12))
            tagIDList.append(tagID)
            fieldTypeList.append(fieldType)
            nValuesList.append(nValues)
            if nValues == 1:
                ftype, vfmt = FIELD_TYPE[fieldType]
                if ftype not in ['ASCII', 'RATIONAL', 'SRATIONAL']:
                    vfmt = st + vfmt
                    actualValue = struct.unpack(vfmt, valueOffset[0: struct.calcsize(vfmt)])[0]
                    valueOffsetList.append(actualValue)
                else:
                    valueOffsetList.append(valueOffset)
            elif (nValues < 5) and (fieldType == 2):
                ftype, vfmt = FIELD_TYPE[fieldType]
                vfmt = st + "%d%s" % (nValues,vfmt)
                actualValue = struct.unpack(vfmt, valueOffset[0: struct.calcsize(vfmt)])[0]
                valueOffsetList.append(actualValue)
            else:
                valueOffsetList.append(valueOffset)
            if DEBUG:
                if tagID in TAG_ID:
                    print("tagID = %s" % TAG_ID[tagID])
                else:
                    print("tagID        = %d" % tagID)
                print("fieldType    = %s" % FIELD_TYPE[fieldType][0])
                print("nValues      = %d" % nValues)
                #if nValues == 1:
                #    print("valueOffset =  %s" % valueOffset)
        return tagIDList, fieldTypeList, nValuesList, valueOffsetList



    def _readIFDEntry(self, tag, tagIDList, fieldTypeList, nValuesList, valueOffsetList):
        fd = self.fd
        st = self._structChar
        idx = tagIDList.index(tag)
        nValues = nValuesList[idx]
        output = []
        ftype, vfmt = FIELD_TYPE[fieldTypeList[idx]]
        vfmt = st + "%d%s" % (nValues, vfmt)
        requestedBytes = struct.calcsize(vfmt)
        if nValues ==  1:
            output.append(valueOffsetList[idx])
        elif requestedBytes < 5:
            output.append(valueOffsetList[idx])
        else:
            offset = fd.seek(struct.unpack(st+"I", valueOffsetList[idx])[0])
            output = struct.unpack(vfmt, fd.read(requestedBytes))
        return output

    def getData(self, nImage, **kw):
        if nImage >= len(self._IFD):
            #update prior to raise an index error error
            self._updateIFD()
        return self._readImage(nImage, **kw)

    def getImage(self, nImage):
        return self.getData(nImage)

    def getInfo(self, nImage, **kw):
        if nImage >= len(self._IFD):
            #update prior to raise an index error error
            self._updateIFD()
        current = self._IFD[nImage]
        return self._readInfo(nImage)

    def _readInfo(self, nImage, close=True):
        if nImage in self._imageInfoCacheIndex:
            if DEBUG:
                print("Reading info from cache")
            return self._imageInfoCache[self._imageInfoCacheIndex.index(nImage)]

        #read the header
        self.__makeSureFileIsOpen()
        tagIDList, fieldTypeList, nValuesList, valueOffsetList = self._parseImageFileDirectory(nImage)
        
        #rows and columns
        nColumns = valueOffsetList[tagIDList.index(TAG_NUMBER_OF_COLUMNS)]
        nRows    = valueOffsetList[tagIDList.index(TAG_NUMBER_OF_ROWS)]

        #bits per sample
        idx = tagIDList.index(TAG_BITS_PER_SAMPLE)
        nBits = valueOffsetList[idx]
        if nValuesList[idx] != 1:
            #this happens with RGB and friends, nBits is not a single value
            nBits = self._readIFDEntry(TAG_BITS_PER_SAMPLE,
                                          tagIDList, fieldTypeList, nValuesList, valueOffsetList)

        #sample format
        if TAG_SAMPLE_FORMAT in tagIDList:
            sampleFormat = valueOffsetList[tagIDList.index(TAG_SAMPLE_FORMAT)]
        else:
            #set to unknown
            sampleFormat = SAMPLE_FORMAT_VOID

        # compression
        compression = False
        if TAG_COMPRESSION in tagIDList:
            if valueOffsetList[tagIDList.index(TAG_COMPRESSION)] == 1:
                compression = False
            else:
                compression = True

        #photometric interpretation
        interpretation = valueOffsetList[tagIDList.index(TAG_PHOTOMETRIC_INTERPRETATION)]
        helpString = ""
        if sys.version > '2.6':
            helpString = eval('b""')

        if TAG_IMAGE_DESCRIPTION in tagIDList:
            imageDescription = self._readIFDEntry(TAG_IMAGE_DESCRIPTION,
                    tagIDList, fieldTypeList, nValuesList, valueOffsetList)
            if type(imageDescription) in [type([1]), type((1,))]:
                imageDescription =helpString.join(imageDescription)
        else:
            imageDescription = "%d/%d" % (nImage+1, len(self._IFD))

        if sys.version < '3.0':
            defaultSoftware = "Unknown Software"            
        else:
            defaultSoftware = bytes("Unknown Software",
                                    encoding='utf-8')
        if TAG_SOFTWARE in tagIDList:
            software = self._readIFDEntry(TAG_SOFTWARE,
                    tagIDList, fieldTypeList, nValuesList, valueOffsetList)
            if type(software) in [type([1]), type((1,))]:
                software =helpString.join(software)
        else:
            software = defaultSoftware

        if software == defaultSoftware:
            try:
                if sys.version < '3.0':
                    if imageDescription.upper().startswith("IMAGEJ"):
                        software = imageDescription.split("=")[0]
                else:
                    tmpString = imageDescription.decode()
                    if tmpString.upper().startswith("IMAGEJ"):
                        software = bytes(tmpString.split("=")[0],
                                         encoding='utf-8')
            except:
                pass

        if TAG_DATE in tagIDList:
            date = self._readIFDEntry(TAG_DATE,
                    tagIDList, fieldTypeList, nValuesList, valueOffsetList)
            if type(date) in [type([1]), type((1,))]:
                date =helpString.join(date)
        else:
            date = "Unknown Date"
        
        stripOffsets = self._readIFDEntry(TAG_STRIP_OFFSETS,
                        tagIDList, fieldTypeList, nValuesList, valueOffsetList)
        rowsPerStrip = self._readIFDEntry(TAG_ROWS_PER_STRIP,
                        tagIDList, fieldTypeList, nValuesList, valueOffsetList)[0]
        stripByteCounts = self._readIFDEntry(TAG_STRIP_BYTE_COUNTS,
                        tagIDList, fieldTypeList, nValuesList, valueOffsetList)
        if close:
            self.__makeSureFileIsClosed()

        info = {}
        info["nRows"] = nRows
        info["nColumns"] = nColumns
        info["nBits"] = nBits
        info["compression"] = compression
        info["imageDescription"] = imageDescription
        info["stripOffsets"] = stripOffsets #This contains the file offsets to the data positions
        info["rowsPerStrip"] = rowsPerStrip
        info["stripByteCounts"] = stripByteCounts #bytes in strip since I do not support compression
        info["software"] = software
        info["date"] = date
        info["sampleFormat"] = sampleFormat
        info["photometricInterpretation"] = interpretation
        infoDict = {}
        if sys.version < '3.0':
            testString = 'PyMca'
        else:
            testString = eval('b"PyMca"')
        if software.startswith(testString):
            #str to make sure python 2.x sees it as string and not unicode
            if sys.version < '3.0':
                descriptionString = imageDescription
            else:
                descriptionString = str(imageDescription.decode())
            #interpret the image description in terms of supplied
            #information at writing time
            items = descriptionString.split('=')
            for i in range(int(len(items)/2)):
                key = "%s" % items[i*2]
                #get rid of the \n at the end of the value 
                value = "%s" % items[i*2+1][:-1] 
                infoDict[key] = value
        info['info'] = infoDict

        self._imageInfoCacheIndex.insert(0,nImage)
        self._imageInfoCache.insert(0, info)
        if len(self._imageInfoCacheIndex) > self._maxImageCacheLength:
            self._imageInfoCacheIndex = self._imageInfoCacheIndex[:self._maxImageCacheLength]
            self._imageInfoCache = self._imageInfoCache[:self._maxImageCacheLength]
        return info

    def _readImage(self, nImage, **kw):
        if DEBUG:
            print("Reading image %d" % nImage)
        if 'close' in kw:
            close = kw['close']
        else:
            close = True
        rowMin = kw.get('rowMin', None)
        rowMax = kw.get('rowMax', None)
        if nImage in self._imageDataCacheIndex:
            if DEBUG:
                print("Reading image data from cache")
            return self._imageDataCache[self._imageDataCacheIndex.index(nImage)]

        self.__makeSureFileIsOpen()
        info = self._readInfo(nImage, close=False)
        compression = info['compression']
        if compression:
            raise IOError("Compressed TIFF images not supported")
        
        interpretation = info["photometricInterpretation"]
        if interpretation > 2:
            raise IOError("Only grey scale images supported")

        nRows    = info["nRows"]
        nColumns = info["nColumns"]
        nBits    = info["nBits"]
        sampleFormat   = info["sampleFormat"]

        if rowMin is None:
            rowMin = 0

        if rowMax is None:
            rowMax = nRows - 1

        if rowMin < 0:
            rowMin = nRows - rowMin

        if rowMax < 0:
            rowMax = nRows - rowMax

        if rowMax < rowMin:
            txt = "Max Row smaller than Min Row. Reverse selection not supported"
            raise NotImplemented(txt)

        if rowMin >= nRows:
            raise IndexError("Image only has %d rows" % nRows)

        if rowMax >= nRows:
            raise IndexError("Image only has %d rows" % nRows)
        
        if sampleFormat == SAMPLE_FORMAT_FLOAT:
            if nBits == 32:
                dtype = numpy.float32
            elif nBits == 64:
                dtype = numpy.float64
            else:
                raise ValueError("Unsupported number of bits for a float: %d" % nBits)
        elif sampleFormat in [SAMPLE_FORMAT_UINT, SAMPLE_FORMAT_VOID]:
            if nBits == 8:
                dtype = numpy.uint8
            elif nBits == 16:
                dtype = numpy.uint16
            elif nBits == 32:
                dtype = numpy.uint32
            elif nBits == 64:
                dtype = numpy.uint64
            else:
                raise ValueError("Unsupported number of bits for unsigned int: %d" % nBits)
        elif sampleFormat == SAMPLE_FORMAT_INT:
            if nBits == 8:
                dtype = numpy.int8
            elif nBits == 16:
                dtype = numpy.int16
            elif nBits == 32:
                dtype = numpy.int32
            elif nBits == 64:
                dtype = numpy.int64
            else:
                raise ValueError("Unsupported number of bits for signed int: %d" % nBits)
        else:
            raise ValueError("Unsupported combination. Bits = %d  Format = %d" % (nBits, sampleFormat))
        image = numpy.zeros((nRows, nColumns), dtype=dtype)

        fd = self.fd
        st = self._structChar
        stripOffsets = info["stripOffsets"] #This contains the file offsets to the data positions
        rowsPerStrip = info["rowsPerStrip"]
        stripByteCounts = info["stripByteCounts"] #bytes in strip since I do not support compression
        rowStart = 0
        if len(stripOffsets) == 1:
            bytesPerRow = int(stripByteCounts[0]/rowsPerStrip)
            fd.seek(stripOffsets[0] + rowMin * bytesPerRow)
            nBytes = (rowMax-rowMin+1) * bytesPerRow
            readout = numpy.fromstring(fd.read(nBytes), dtype)
            readout.shape = -1, nColumns
            if self._swap:
                image[rowMin:rowMax+1, :] = readout.byteswap()
            else:
                image[rowMin:rowMax+1, :] = readout
        else:
            for i in range(len(stripOffsets)):
                #the amount of rows
                nRowsToRead = rowsPerStrip
                rowEnd = int(min(rowStart+nRowsToRead, nRows))
                if rowEnd < rowMin:
                    rowStart += nRowsToRead
                    continue
                if (rowStart > rowMax):
                    break
                #we are in position
                fd.seek(stripOffsets[i])
                #the amount of bytes to read
                nBytes = stripByteCounts[i]
                if 1:
                    readout = numpy.fromstring(fd.read(nBytes), dtype)
                    readout.shape = -1, nColumns
                    if self._swap:
                        image[rowStart:rowEnd, :] = readout.byteswap()
                    else:
                        image[rowStart:rowEnd, :] = readout
                else:
                    readout = numpy.array(struct.unpack(st+"%df" % int(nBytes/4), fd.read(nBytes)),
                                          dtype=dtype)
                    readout.shape = -1, nColumns
                    image[rowStart:rowEnd, :] = readout
                rowStart += nRowsToRead
        if close:
            self.__makeSureFileIsClosed()
        if (rowMin == 0) and (rowMax == (nRows-1)):
            self._imageDataCacheIndex.insert(0,nImage)
            self._imageDataCache.insert(0, image)
            if len(self._imageDataCacheIndex) > self._maxImageCacheLength:
                self._imageDataCacheIndex = self._imageDataCacheIndex[:self._maxImageCacheLength]
                self._imageDataCache = self._imageDataCache[:self._maxImageCacheLength]
        return image

    def writeImage(self, image0, info=None, software=None, date=None):
        if software is None:
            software = 'PyMca.TiffIO'
        #if date is None:
        #    date = time.ctime()

        self.__makeSureFileIsOpen()
        fd = self.fd
        #prior to do anything, perform some tests
        if not len(image0.shape):
            raise ValueError("Empty image")
        if len(image0.shape) == 1:
            #get a different view
            image = image0[:]
            image.shape = 1, -1
        else:
            image = image0
            
        if image.dtype == numpy.float64:
            image = image.astype(numpy.float32)
        fd.seek(0)
        mode = fd.mode
        name = fd.name
        if 'w' in mode:
            #we have to overwrite the file
            self.__makeSureFileIsClosed()
            fd = None
            if os.path.exists(name):
                os.remove(name)
            fd = open(name, mode='wb+')
            self._initEmptyFile(fd)
        self.fd = fd

        #read the file size
        self.__makeSureFileIsOpen()
        fd = self.fd
        fd.seek(0, os.SEEK_END)
        endOfFile = fd.tell()
        if fd.tell() == 0:
            self._initEmptyFile(fd)
            fd.seek(0, os.SEEK_END)
            endOfFile = fd.tell()
        
        #init internal variables
        self._initInternalVariables(fd)
        st = self._structChar
                
        #get the image file directories
        nImages = self.getImageFileDirectories()
        if DEBUG:
            print("File contains %d images" % nImages)
        if nImages == 0:
            fd.seek(4)
            fmt = st + 'I'
            fd.write(struct.pack(fmt, endOfFile))
        else:
            fd.seek(self._IFD[-1])
            fmt = st + 'H'
            numberOfDirectoryEntries = struct.unpack(fmt,fd.read(struct.calcsize(fmt)))[0]
            fmt = st + 'I'
            pos = self._IFD[-1] + 2 + 12 * numberOfDirectoryEntries
            fd.seek(pos)
            fmt = st + 'I'
            fd.write(struct.pack(fmt, endOfFile))
        fd.flush()

        #and we can write at the end of the file, find out the file length
        fd.seek(0, os.SEEK_END)

        #get the description information from the input information
        if info is None:
            description = info
        else:
            description = "%s" % ""
            for key in info.keys():
                description += "%s=%s\n"  % (key, info[key])

        #get the image file directory
        outputIFD = self._getOutputIFD(image, description=description,
                                              software=software,
                                              date=date)

        #write the new IFD
        fd.write(outputIFD)

        #write the image
        if self._swap:
            fd.write(image.byteswap().tostring())
        else:
            fd.write(image.tostring())

        fd.flush()
        self.fd=fd
        self.__makeSureFileIsClosed()

    def _initEmptyFile(self, fd=None):
        if fd is None:
            fd = self.fd
        if sys.byteorder == "little":
            order = "II"
            #intel, little endian
            fileOrder = "little"
            self._structChar = '<'
        else:
            order = "MM"
            #motorola, high endian
            fileOrder = "big"
            self._structChar = '>'
        st = self._structChar
        if fileOrder == sys.byteorder:  
            self._swap = False
        else:
            self._swap = True
        fd.seek(0)
        fd.write(struct.pack(st+'2s', order))
        fd.write(struct.pack(st+'H', 42))
        fd.write(struct.pack(st+'I', 0))
        fd.flush()

    def _getOutputIFD(self, image, description=None, software=None, date=None):
        #the tags have to be in order
        #the very minimum is
        #256:"NumberOfColumns",           # S or L ImageWidth
        #257:"NumberOfRows",              # S or L ImageHeight
        #258:"BitsPerSample",             # S Number of bits per component
        #259:"Compression",               # SHORT (1 - NoCompression, ... 
        #262:"PhotometricInterpretation", # SHORT (0 - WhiteIsZero, 1 -BlackIsZero, 2 - RGB, 3 - Palette color
        #270:"ImageDescription",          # ASCII
        #273:"StripOffsets",              # S or L, for each strip, the byte offset of the strip
        #278:"RowsPerStrip",              # S or L, number of rows in each back may be not for the last
        #279:"StripByteCounts",           # S or L, The number of bytes in the strip AFTER any compression
        #305:"Software",                  # ASCII
        #306:"Date",                      # ASCII
        #339:"SampleFormat",              # SHORT Interpretation of data in each pixel
    
        nDirectoryEntries = 9
        imageDescription = None
        if description is not None:
            descriptionLength = len(description)
            while descriptionLength < 4:
                description = description + " "
                descriptionLength = len(description)
            imageDescription = struct.pack("%ds" % descriptionLength, description)
            nDirectoryEntries += 1

        #software
        if software is not None:
            softwareLength = len(software)
            while softwareLength < 4:
                software = software + " "
                softwareLength = len(software)
            softwarePackedString = struct.pack("%ds" % softwareLength, software)
            nDirectoryEntries += 1
        else:
            softwareLength = 0

        if date is not None:
            dateLength = len(date)
            datePackedString = struct.pack("%ds" % dateLength, date)
            dateLength = len(datePackedString)
            nDirectoryEntries += 1
        else:
            dateLength = 0
            
        nRows, nColumns = image.shape
        dtype = image.dtype
        bitsPerSample = int(dtype.str[-1]) * 8

        #only uncompressed data
        compression = 1

        #interpretation, black is zero
        interpretation = 1

        #image description
        if imageDescription is not None:
            descriptionLength = len(imageDescription)
        else:
            descriptionLength = 0

        #strip offsets
        #we are putting them after the directory and the directory is
        #at the end of the file
        self.fd.seek(0, os.SEEK_END)
        endOfFile = self.fd.tell()
        if endOfFile == 0:
            #empty file
            endOfFile = 8

        #rows per strip
        if ALLOW_MULTIPLE_STRIPS:
            #try to segment the image in several pieces
            if not (nRows % 4):
                rowsPerStrip = int(nRows/4)
            elif not (nRows % 10):
                rowsPerStrip = int(nRows/10)
            elif not (nRows % 8):
                rowsPerStrip = int(nRows/8)
            elif not (nRows % 4):
                rowsPerStrip = int(nRows/4)
            elif not (nRows % 2):
                rowsPerStrip = int(nRows/2)
            else:
                rowsPerStrip = nRows
        else:
            rowsPerStrip = nRows

        #stripByteCounts
        stripByteCounts = int(nColumns * rowsPerStrip * bitsPerSample / 8)

        if descriptionLength > 4:
            stripOffsets0 = endOfFile + dateLength + descriptionLength +\
                        2 + 12 * nDirectoryEntries + 4
        else:
            stripOffsets0 = endOfFile + dateLength + \
                        2 + 12 * nDirectoryEntries + 4

        if softwareLength > 4:
            stripOffsets0 += softwareLength

        stripOffsets = [stripOffsets0]
        stripOffsetsLength = 0
        stripOffsetsString = None

        st = self._structChar

        if rowsPerStrip != nRows:
            nStripOffsets = int(nRows/rowsPerStrip)
            fmt = st + 'I'
            stripOffsetsLength = struct.calcsize(fmt) * nStripOffsets 
            stripOffsets0 += stripOffsetsLength
            #the length for the stripByteCounts will be the same
            stripOffsets0 += stripOffsetsLength
            stripOffsets = []
            for i in range(nStripOffsets):
                value = stripOffsets0 + i * stripByteCounts
                stripOffsets.append(value)
                if i == 0:
                    stripOffsetsString  = struct.pack(fmt, value)
                    stripByteCountsString = struct.pack(fmt, stripByteCounts)
                else:
                    stripOffsetsString += struct.pack(fmt, value)
                    stripByteCountsString += struct.pack(fmt, stripByteCounts)
            
        if DEBUG:
            print("IMAGE WILL START AT %d" % stripOffsets[0])
            
        #sample format
        if dtype in [numpy.float32, numpy.float64] or\
           dtype.str[-2] == 'f':
            sampleFormat = SAMPLE_FORMAT_FLOAT
        elif dtype in [numpy.uint8, numpy.uint16, numpy.uint32, numpy.uint64]:
            sampleFormat = SAMPLE_FORMAT_UINT
        elif dtype in [numpy.int8, numpy.int16, numpy.int32, numpy.int64]:
            sampleFormat = SAMPLE_FORMAT_INT
        else:
            raise ValueError("Unsupported data type %s" % dtype)

        info = {}
        info["nColumns"] = nColumns
        info["nRows"] = nRows
        info["nBits"] = bitsPerSample
        info["compression"] = compression
        info["photometricInterpretation"] = interpretation
        info["stripOffsets"] = stripOffsets
        info["rowsPerStrip"] = rowsPerStrip
        info["stripByteCounts"] = stripByteCounts
        info["date"] = date
        info["sampleFormat"] = sampleFormat
        
        outputIFD = ""
        if sys.version > '2.6':
            outputIFD = eval('b""')
        
        fmt = st + "H"
        outputIFD += struct.pack(fmt, nDirectoryEntries)

        fmt = st + "HHII"
        outputIFD += struct.pack(fmt, TAG_NUMBER_OF_COLUMNS,
                                         FIELD_TYPE_OUT['I'],
                                         1,
                                         info["nColumns"])
        outputIFD += struct.pack(fmt, TAG_NUMBER_OF_ROWS,
                                         FIELD_TYPE_OUT['I'],
                                         1,
                                         info["nRows"])
        
        fmt = st + 'HHIHH'
        outputIFD += struct.pack(fmt, TAG_BITS_PER_SAMPLE,
                                         FIELD_TYPE_OUT['H'],
                                         1,
                                         info["nBits"],0)
        fmt = st + 'HHIHH'
        outputIFD += struct.pack(fmt, TAG_COMPRESSION,
                                         FIELD_TYPE_OUT['H'],
                                         1,
                                         info["compression"],0)
        fmt = st + 'HHIHH'
        outputIFD += struct.pack(fmt, TAG_PHOTOMETRIC_INTERPRETATION,
                                         FIELD_TYPE_OUT['H'],
                                         1,
                                         info["photometricInterpretation"],0)

        if imageDescription is not None:
            descriptionLength = len(imageDescription)
            if descriptionLength > 4:
                fmt = st + 'HHII'
                outputIFD += struct.pack(fmt, TAG_IMAGE_DESCRIPTION,
                                         FIELD_TYPE_OUT['s'],
                                         descriptionLength,
                                         info["stripOffsets"][0]-\
                                         2*stripOffsetsLength-\
                                         descriptionLength)
            else:
                #it has to have length 4
                fmt = st + 'HHI%ds' % descriptionLength
                outputIFD += struct.pack(fmt, TAG_IMAGE_DESCRIPTION,
                                         FIELD_TYPE_OUT['s'],
                                         descriptionLength,
                                         description)

        if len(stripOffsets) == 1:
            fmt = st + 'HHII'
            outputIFD += struct.pack(fmt, TAG_STRIP_OFFSETS,
                                             FIELD_TYPE_OUT['I'],
                                             1,
                                             info["stripOffsets"][0])
        else:
            fmt = st + 'HHII'
            outputIFD += struct.pack(fmt, TAG_STRIP_OFFSETS,
                                             FIELD_TYPE_OUT['I'],
                                             len(stripOffsets),
                    info["stripOffsets"][0]-2*stripOffsetsLength)

        fmt = st + 'HHII'
        outputIFD += struct.pack(fmt, TAG_ROWS_PER_STRIP,
                                         FIELD_TYPE_OUT['I'],
                                         1,
                                         info["rowsPerStrip"])

        if len(stripOffsets) == 1:
            fmt = st + 'HHII'
            outputIFD += struct.pack(fmt, TAG_STRIP_BYTE_COUNTS,
                                             FIELD_TYPE_OUT['I'],
                                             1,
                                             info["stripByteCounts"])
        else:
            fmt = st + 'HHII'
            outputIFD += struct.pack(fmt, TAG_STRIP_BYTE_COUNTS,
                                             FIELD_TYPE_OUT['I'],
                                             len(stripOffsets),
                    info["stripOffsets"][0]-stripOffsetsLength)

        if software is not None:
            if softwareLength > 4:
                fmt = st + 'HHII'
                outputIFD += struct.pack(fmt, TAG_SOFTWARE,
                                         FIELD_TYPE_OUT['s'],
                                         softwareLength,
                                         info["stripOffsets"][0]-\
                                         2*stripOffsetsLength-\
                            descriptionLength-softwareLength-dateLength)
            else:
                #it has to have length 4
                fmt = st + 'HHI%ds' % softwareLength
                outputIFD += struct.pack(fmt, TAG_SOFTWARE,
                                         FIELD_TYPE_OUT['s'],
                                         softwareLength,
                                         softwarePackedString)            

        if date is not None:
            fmt = st + 'HHII'
            outputIFD += struct.pack(fmt, TAG_DATE,
                                      FIELD_TYPE_OUT['s'],
                                      dateLength,
                                      info["stripOffsets"][0]-\
                                         2*stripOffsetsLength-\
                                      descriptionLength-dateLength)

        fmt = st + 'HHIHH'
        outputIFD += struct.pack(fmt, TAG_SAMPLE_FORMAT,
                                         FIELD_TYPE_OUT['H'],
                                         1,
                                         info["sampleFormat"],0)
        fmt = st + 'I'
        outputIFD += struct.pack(fmt, 0)

        if softwareLength > 4:
            outputIFD += softwarePackedString

        if date is not None:
            outputIFD += datePackedString
        
        if imageDescription is not None:
            if descriptionLength > 4:
                outputIFD += imageDescription

        if stripOffsetsString is not None:
            outputIFD += stripOffsetsString
            outputIFD += stripByteCountsString

        return outputIFD

     
if __name__ == "__main__":
    filename = sys.argv[1]
    dtype = numpy.uint16
    if not os.path.exists(filename):
        print("Testing file creation")
        tif = TiffIO(filename, mode = 'wb+')
        data = numpy.arange(10000).astype(dtype)
        data.shape = 100, 100
        tif.writeImage(data, info={'Title':'1st'})
        tif = None
        if os.path.exists(filename):
            print("Testing image appending")
            tif = TiffIO(filename, mode = 'rb+')
            tif.writeImage((data*2).astype(dtype), info={'Title':'2nd'})
            tif = None
    tif = TiffIO(filename)
    print("Number of images = %d" % tif.getNumberOfImages())
    for i in range(tif.getNumberOfImages()):
        info = tif.getInfo(i)
        for key in info:
            print("%s = %s" % (key, info[key]))
        data = tif.getImage(i)[0, 0:10]
        print ("data [0, 0:10] = ", data)
    
