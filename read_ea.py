import sys
import struct
import array
from os.path import join, exists
import os
import numpy as np
import tempfile
import h5py
import pandas as pd
import os
import ftplib
import gzip
import tarfile
from os.path import join
import shutil
############################    MET OFFICE CODE    ############################

class Nimrod:
    """Reading, querying and processing of NIMROD format rainfall data files."""

    class RecordLenError(Exception):
        """S
        Exception Type: NIMROD record length read from file not as expected.
        """

        def __init__(self, actual, expected, location):
            self.message = (
                    "Incorrect record length %d bytes (expected %d) at %s."
                    % (actual, expected, location))

    class HeaderReadError(Exception):
        """Exception Type: Read error whilst parsing NIMROD header elements."""
        pass

    class PayloadReadError(Exception):
        """Exception Type: Read error whilst parsing NIMROD raster data."""
        pass

    class BboxRangeError(Exception):
        """
        Exception Type: Bounding box specified out of range of raster image.
        """
        pass

    def __init__(self, infile):
        """
        Parse all header and data info from a NIMROD data file into this object.
        (This method based on read_nimrod.py by Charles Kilburn Aug 2008)

        Args:
            infile: NIMROD file object opened for binary reading
        Raises:
            RecordLenError: NIMROD record length read from file not as expected
            HeaderReadError: Read error whilst parsing NIMROD header elements
            PayloadReadError: Read error whilst parsing NIMROD raster data
        """

        def check_record_len(infile, expected, location):
            """
            Check record length in C struct is as expected.

            Args:
                infile: file to read from
                expected: expected value of record length read
                location: description of position in file (for reporting)
            Raises:
                HeaderReadError: Read error whilst reading record length
                RecordLenError: Unexpected NIMROD record length read from file
            """

            # Unpack length from C struct (Big Endian, 4-byte long)
            try:
                record_length, = struct.unpack(">l", infile.read(4))
            except Exception:
                raise Nimrod.HeaderReadError
            if record_length != expected:
                raise Nimrod.RecordLenError(record_length, expected, location)

        # Header should always be a fixed length record
        check_record_len(infile, 512, "header start")

        # try:
        # Read first 31 2-byte integers (header fields 1-31)
        gen_ints = array.array("h")
        gen_ints.fromfile(infile, 31)
        gen_ints.byteswap()

        # Read next 28 4-byte floats (header fields 32-59)
        gen_reals = array.array("f")
        gen_reals.fromfile(infile, 28)
        gen_reals.byteswap()

        # Read next 45 4-byte floats (header fields 60-104)
        spec_reals = array.array("f")
        spec_reals.fromfile(infile, 45)
        spec_reals.byteswap()

        # Read next 56 characters (header fields 105-107)
        characters = array.array("b")
        characters.fromfile(infile, 56)

        # Read next 51 2-byte integers (header fields 108-)
        spec_ints = array.array("h")
        spec_ints.fromfile(infile, 51)
        spec_ints.byteswap()
        # except Exception:
        #     infile.close()
        #     raise Nimrod.HeaderReadError

        check_record_len(infile, 512, "header end")

        # Extract strings and make duplicate entries to give meaningful names
        chars = characters.tobytes()
        self.units = chars[0:8]
        self.data_source = chars[8:32]
        self.title = chars[32:55]

        # Store header values in a list so they can be indexed by "element
        # number" shown in NIMROD specification (starts at 1)
        self.hdr_element = [None]  # Dummy value at element 0
        self.hdr_element.extend(gen_ints)
        self.hdr_element.extend(gen_reals)
        self.hdr_element.extend(spec_reals)
        self.hdr_element.extend([self.units])
        self.hdr_element.extend([self.data_source])
        self.hdr_element.extend([self.title])
        self.hdr_element.extend(spec_ints)

        # Duplicate some of values to give more meaningful names
        self.nrows = self.hdr_element[16]
        self.ncols = self.hdr_element[17]
        self.n_data_specific_reals = self.hdr_element[22]
        self.n_data_specific_ints = self.hdr_element[23] + 1
        # Note "+ 1" because header value is count from element 109
        self.y_top = self.hdr_element[34]
        self.y_pixel_size = self.hdr_element[35]
        self.x_left = self.hdr_element[36]
        self.x_pixel_size = self.hdr_element[37]

        # Calculate other image bounds (note these are pixel centres)
        self.x_right = (self.x_left + self.x_pixel_size * (self.ncols - 1))
        self.y_bottom = (self.y_top - self.y_pixel_size * (self.nrows - 1))

        # Read payload (actual raster data)
        array_size = self.ncols * self.nrows
        check_record_len(infile, array_size * 2, "data start")

        self.data = array.array("h")
        try:
            self.data.fromfile(infile, array_size)
            self.data.byteswap()
        except Exception:
            infile.close()
            raise Nimrod.PayloadReadError

        check_record_len(infile, array_size * 2, "data end")
        infile.close()

    def query(self):
        """Print complete NIMROD file header information."""

        print("NIMROD file raw header fields listed by element number:")
        print("General (Integer) header entries:")
        for i in range(1, 32):
            print(" ", i, "\t", self.hdr_element[i])
        print("General (Real) header entries:")
        for i in range(32, 60):
            print(" ", i, "\t", self.hdr_element[i])
        print(("Data Specific (Real) header entries (%d):"
               % self.n_data_specific_reals))
        for i in range(60, 60 + self.n_data_specific_reals):
            print(" ", i, "\t", self.hdr_element[i])
        print(("Data Specific (Integer) header entries (%d):"
               % self.n_data_specific_ints))
        for i in range(108, 108 + self.n_data_specific_ints):
            print(" ", i, "\t", self.hdr_element[i])
        print("Character header entries:")
        print("  105 Units:           ", self.units)
        print("  106 Data source:     ", self.data_source)
        print("  107 Title of field:  ", self.title)

        # Print out info & header fields
        # Note that ranges are given to the edge of each pixel
        print("\nValidity Time:  %2.2d:%2.2d on %2.2d/%2.2d/%4.4d" % (
            self.hdr_element[4], self.hdr_element[5],
            self.hdr_element[3], self.hdr_element[2], self.hdr_element[1]))
        print(("Easting range:  %.1f - %.1f (at pixel steps of %.1f)"
               % (self.x_left - self.x_pixel_size / 2,
                  self.x_right + self.x_pixel_size / 2, self.x_pixel_size)))
        print(("Northing range: %.1f - %.1f (at pixel steps of %.1f)"
               % (self.y_bottom - self.y_pixel_size / 2,
                  self.y_top + self.y_pixel_size / 2, self.y_pixel_size)))
        print("Image size: %d rows x %d cols" % (self.nrows, self.ncols))

    def apply_bbox(self, xmin, xmax, ymin, ymax):
        """
        Clip raster data to all pixels that intersect specified bounding box.

        Note that existing object data is modified and all header values
        affected are appropriately adjusted. Because pixels are specified by
        their centre points, a bounding box that comes within half a pixel
        width of the raster edge will intersect with the pixel.

        Args:
            xmin: Most negative easting or longitude of bounding box
            xmax: Most positive easting or longitude of bounding box
            ymin: Most negative northing or latitude of bounding box
            ymax: Most positive northing or latitude of bounding box
        Raises:
            BboxRangeError: Bounding box specified out of range of raster image
        """

        # Check if there is no overlap of bounding box with raster
        if (
                xmin > self.x_right + self.x_pixel_size / 2 or
                xmax < self.x_left - self.x_pixel_size / 2 or
                ymin > self.y_top + self.y_pixel_size / 2 or
                ymax < self.y_bottom - self.x_pixel_size / 2):
            raise Nimrod.BboxRangeError

        # Limit bounds to within raster image
        xmin = max(xmin, self.x_left)
        xmax = min(xmax, self.x_right)
        ymin = max(ymin, self.y_bottom)
        ymax = min(ymax, self.y_top)

        # Calculate min and max pixel index in each row and column to use
        # Note addition of 0.5 as x_left location is centre of pixel
        # ('int' truncates floats towards zero)
        xMinPixelId = int((xmin - self.x_left) / self.x_pixel_size + 0.5)
        xMaxPixelId = int((xmax - self.x_left) / self.x_pixel_size + 0.5)

        # For y (northings), note the first data row stored is most north
        yMinPixelId = int((self.y_top - ymax) / self.y_pixel_size + 0.5)
        yMaxPixelId = int((self.y_top - ymin) / self.y_pixel_size + 0.5)

        bbox_data = []
        for i in range(yMinPixelId, yMaxPixelId + 1):
            bbox_data.extend(self.data[i * self.ncols + xMinPixelId:
                                       i * self.ncols + xMaxPixelId + 1])

        # Update object where necessary
        self.data = bbox_data
        self.x_right = self.x_left + xMaxPixelId * self.x_pixel_size
        self.x_left += xMinPixelId * self.x_pixel_size
        self.ncols = xMaxPixelId - xMinPixelId + 1
        self.y_bottom = self.y_top - yMaxPixelId * self.y_pixel_size
        self.y_top -= yMinPixelId * self.y_pixel_size
        self.nrows = yMaxPixelId - yMinPixelId + 1
        self.hdr_element[16] = self.nrows
        self.hdr_element[17] = self.ncols
        self.hdr_element[34] = self.y_top
        self.hdr_element[36] = self.x_left

    def extract_asc(self, outfile):
        """
        Write raster data to an ESRI ASCII (.asc) format file.

        Args:
            outfile: file object opened for writing text
        """

        # As ESRI ASCII format only supports square pixels, warn if not so
        if self.x_pixel_size != self.y_pixel_size:
            print(("Warning: x_pixel_size(%d) != y_pixel_size(%d)"
                   % (self.x_pixel_size, self.y_pixel_size)))

        # Write header to output file. Note that data is valid at the centre
        # of each pixel so "xllcenter" rather than "xllcorner" must be used
        outfile.write("xmin: " + str(self.x_left) + " \n")
        outfile.write("xmax: " + str(self.x_right) + " \n")
        outfile.write("ymin: " + str(self.y_bottom) + " \n")
        outfile.write("ymax: " + str(self.y_top) + " \n")
        outfile.write("ncols: " + str(self.ncols) + " \n")
        outfile.write("nrows: " + str(self.nrows) + " \n")
        outfile.write("cellsize : " + str(self.y_pixel_size) + " \n")
        outfile.write("na_value: " + str(self.hdr_element[38]) + " \n")

        # Write raster data to output file
        for i in range(self.nrows):
            for j in range(self.ncols - 1):
                outfile.write("%d " % self.data[i * self.ncols + j])
            outfile.write("%d\n" % self.data[i * self.ncols + self.ncols - 1])
        outfile.close()


# -------------------------------------------------------------------------------
# Handle if called as a command line script
# (And as an example of how to invoke class methods from an importing module)
# -------------------------------------------------------------------------------

def nimrod_file(file_in, file_out=None, bbox=None, query=False, extract=False):
    try:
        rainfall_data = Nimrod(open(file_in, 'rb'))
        # rainfall_data = Nimrod(file_in)
    except Nimrod.RecordLenError as error:
        sys.stderr.write("ERROR: %s\n" % error.message)
        sys.exit(1)

    if bbox is not None:
        #sys.stderr.write(
        #    "Trimming NIMROD raster to bounding box...\n")
        try:
            rainfall_data.apply_bbox(bbox[0], bbox[1], bbox[2], bbox[3])
        except Nimrod.BboxRangeError:
            sys.stderr.write("ERROR: bounding box not within raster image.\n")
            sys.exit(1)
    # Perform query after any bounding box trimming to allow sanity checking of
    # size of resulting image
    if query:
        rainfall_data.query()

    if extract:
        #sys.stderr.write(
        #    "Extracting NIMROD raster to ASC file...\n")
        # if file_out is None:
        #    file_out = str(file_in) + ".asc"
        #sys.stderr.write(
        #    "  Outputting data array (%d rows x %d cols = %d pixels)\n"
        #    % (rainfall_data.nrows, rainfall_data.ncols,
        #       rainfall_data.nrows * rainfall_data.ncols))
        rainfall_data.extract_asc(open(file_out, 'w'))
    return rainfall_data

################################### MY HELPER FUNCTIONS ######################################

# Function to get file names for input
def get_filenames(date_start, date_end, format='%Y-%m-%d %H:%M:%S'):
    
    # Get start and end dates
    start = pd.to_datetime(date_start, format=format)
    end = pd.to_datetime(date_end, format=format)

    # Get timestamp for files
    dates = pd.date_range(start=start, end=end)
    years = dates.year
    # Get file names
    file_names = []
    for date in dates:
        datestring = str(date)[0:-9].replace('-', '')
        name_string = 'metoffice-c-band-rain-radar_uk_' + datestring + '_1km-composite.dat.gz.tar'
        file_names.append(name_string)
    
    return file_names, years
    
# Function to extract data
def extract(file_from, bbox):
    
    tar_files = [join(file_from, ff) for ff in os.listdir(file_from) if ff.endswith(".tar")]
    
    if len(tar_files) > 0:
        
        dates = []
        arrs = []

        for tf in tar_files:

            with tarfile.open(tf) as tar:
                tar.extractall(file_from)

                gz_files = [join(file_from, ff) for ff in os.listdir(file_from) if ff.endswith(".gz")]

                for g in gz_files:

                    with gzip.open(g, 'rb') as f_in:
                        with open(join(file_from, os.path.splitext(g)[0]), 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                dat_files = [ff for ff in os.listdir(file_from) if ff.endswith(".dat")]

                for df in dat_files:

                    try:
                        nf = nimrod_file(join(file_from, df), 
                                    #join(file_to, df.split(".")[0] + ".asc"), 
                                    bbox=bbox)#, 
                                    #extract=True)
                            
                        xs = pd.Series(np.linspace(nf.x_left, nf.x_right, nf.ncols))
                        ys = pd.Series(np.linspace(nf.y_bottom, nf.y_top, nf.nrows))
                        dates.append(pd.to_datetime(df.split("_")[-2]))
                        arrs.append(np.array(nf.data).reshape(nf.nrows, nf.ncols))

                    except:
                        print("Not worked for ", df)

    return [dates, arrs, xs, ys]

# Function to get data (note: shouldn't be ran for a long time - uses up a lot of storage in temp folder)
def download(start_date, end_date, folder_path, bbox, delete=True):
    
    # If new directory doesn't exist make it
    temp_dir = join(folder_path, "temp")
    if not os.path.isdir(temp_dir):
        os.mkdir(temp_dir)
    
    # Get file names to download 
    file_names, years = get_filenames(start_date, end_date)
    
    for year in list(set(years)):
        file_dir = '/badc/ukmo-nimrod/data/composite/uk-1km/' + str(year) + '/'

        # login to FTP
        f = ftplib.FTP("ftp.ceda.ac.uk", username, password)

        # Directory of files to save
        f.cwd(file_dir)

        for file in np.array(file_names)[years == year]:
            
            try:
                # Copies data from ftp server
                f.retrbinary("RETR %s" % file, open(join(temp_dir, file), "wb").write)
            except:
                print(file, " did not work.")
                
    # Extracts and clips data
    dates, arrs, xs, ys = extract(temp_dir, bbox)
    
    # Save data (horrible way to save it)
    pd.Series(dates).to_csv(join(folder_path, "timestamp.csv"), index=False)
    np.save(join(folder_path, "arrays.npy"), np.array(arrs) / 32)
    xs.to_csv(join(folder_path, "coords_x.csv"), index=False)
    ys.to_csv(join(folder_path, "coords_y.csv"), index=False)
    
    if delete:
        shutil.rmtree(temp_dir)
################################### PARAMETERS TO CHANGE ######################################

# output folder to save files
root_path = r"./save"
output_path = join(root_path, "MET")
if not exists(output_path):
    os.mkdir(output_path)

outpath_15min = join(output_path, "15min")
if not exists(outpath_15min):
    os.mkdir(outpath_15min)
    
# CEDA username and password
username = os.getenv("CEDA_USERNAME")
password = os.getenv("CEDA_PASSWORD")
if username == None or password == None:
        raise EnvironmentError("No CEDA credentials provided")

# dates for files 
start_date = pd.to_datetime("2023-06-20")
end_date = pd.to_datetime("2023-06-30")

# Bounding box for data 
e_l, n_l, e_u, n_u = [355000, 534000, 440000, 609000]
bbox = [e_l, e_u, n_l, n_u]


##############################################################################################

# download and clip files (not this will take a while)
download(start_date, end_date, output_path, bbox, delete=True)

# change temporal resolution of data
timestamp_series = pd.to_datetime(pd.read_csv(join(output_path, "timestamp.csv"))["0"])
arrs = np.load(join(output_path, "arrays.npy"))

# new data resolution in seconds
delta_t = str(15*60) + "s"

start_date = timestamp_series.min().round(delta_t)
end_date = timestamp_series.max().round(delta_t)

new_timestamp = pd.date_range(
    pd.to_datetime(start_date),
    pd.to_datetime(end_date) + pd.Timedelta(1, "d"),
    freq=str(15 * 60) + "s", 
    tz="UTC"
)

new_arrays = np.full((new_timestamp.shape[0], arrs.shape[1], arrs.shape[2]), np.nan)

for i, t in enumerate(new_timestamp):

    cond = (timestamp_series >= t) & (timestamp_series < t + pd.Timedelta(delta_t))
    subset = arrs[cond]
    if subset.shape[0] > 0:
        new_arrays[i] = np.nanmean(subset, axis=0)

xs = pd.read_csv(join(output_path, "coords_x.csv"))
xs.to_csv(join(outpath_15min, "coords_x.csv"), index=False)

ys = pd.read_csv(join(output_path, "coords_y.csv"))
ys.to_csv(join(outpath_15min, "coords_y.csv"), index=False)

pd.Series(new_timestamp).to_csv(join(outpath_15min, "timestamp.csv"), index=False)
np.save(join(outpath_15min, "arrays.npy"), new_arrays)