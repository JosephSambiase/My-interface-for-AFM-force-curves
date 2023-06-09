# Import used for the functions
import os, sys
import numpy as np
import glob
from constants import *
from jpk.loadjpkfile import loadJPKfile
from jpk.loadjpkthermalfile import loadJPKThermalFile
from nanosc.loadnanoscfile import loadNANOSCfile
from load_uff import loadUFFtxt
from uff import UFF
from pyafmrheo.utils.force_curves import *
import numpy as np


# Import used for the interface
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QPushButton, QHBoxLayout, QWidget, QMessageBox
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg

import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set up the main window
        self.setWindowTitle('Plotting datas')
        self.setFixedSize(1280,720)
        
        # Add a menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('File')
        
        # Add a "Open" action to the File menu
        open_action = file_menu.addAction('Open a file')
        open_action.triggered.connect(self.open_file)
        
        # Add a "Plot deflection vs height" action to the File menu
        plot_action = file_menu.addAction('Plot deflection vs height')
        plot_action.triggered.connect(self.plot_data)
        
        # Add a "Plot PoC" action to the File menu
        analyze_action = file_menu.addAction('Plot the point of contact')
        analyze_action.triggered.connect(self.calculate_poc)
        
        # Add a "Open" action to the File menu
        folder_action = file_menu.addAction('Open a folder + plot force vs indentation')
        folder_action.triggered.connect(self.open_folder)
        
        # Activate the button plot in the center of the window
        self.define_buttons()
        self.plot_button.clicked.connect(self.plot_data)
        
        
    # Define the button plot in the center of the window
    def define_buttons(self):
        hbox = QHBoxLayout()
        self.central_widget = QWidget()
        self.central_widget.setLayout(hbox)
        self.setCentralWidget(self.central_widget)
        self.plot_button = QPushButton('Plot deflection vs height')
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.plot_button)
        hbox.addWidget(self.plot_button)
        

    # Function used to open a file 
    def open_file(self):

        # Show a file dialog to select a file
        filename, _ = QFileDialog.getOpenFileName(self, 'Open File', '', 'All files (*.*)')
        self.file = self.loadfile(filename)


    # Function used to open a folder
    def open_folder(self):
        dirname = QFileDialog.getExistingDirectory(
				self, 'Choose Directory', r'./'
			)
        if dirname != "" and dirname is not None:
            valid_files = self.getFileList(dirname)
            if valid_files != []:
                indentation = []
                k=0 # k is the number of .jpk-force files
                list_bins=[]
                
                # We make a loop to plot the force vs indentation for every file
                for filename in glob.glob(os.path.join(dirname, '*.jpk-force')):                  
                    self.file = self.loadfile(filename)
                    self.collectData()
                    self.plot_force()    
                    k=k+1

                    bin_size = 10e-9 # Set the bin size
                    bins = int(max(self.app_force) / bin_size) + 1  # Calculate the number of bins
                    list_bins.append(bins)
                    
                    # The files can have differentsame number of bins. So we take the number of bins equals to the one that is the smallest
                    list_bins.sort()
                    n_bins=list_bins[0]
                    
           
                    # We recover every indentations that are in every bin. Here it recovers indentations from 0-10 nN then 10-20 nN etc...
                    for i in range(n_bins+1):
                        lower_limit = i * bin_size
                        upper_limit = (i + 1) * bin_size
                        mask = (self.app_force >= lower_limit) & (self.app_force < upper_limit) & (self.app_indentation >= 0)
                        indent_range = self.app_indentation[mask]
                        indentation.append(indent_range)
                
                # We convert it in array and split it in k which is the number of files 
                indentation = np.array(indentation)
                indentation = np.array_split(indentation, k)
  
                # Here we calculate the mean of the indentations recovered previously for every file
                list_mean = []
                for i in range (k):
                    for j in range(n_bins):
                        arr = np.array(indentation[i][j])
                        list_mean.append(np.mean(arr))
                
                # We convert it in array and split in in  k
                list_mean=np.array(list_mean)
                list_mean=np.array_split(list_mean, k)                
                
                # Now we sum the bins from every file and make a mean. Sum of the indentation from 0-10 nN from every file divided by the number of files etc...
                sum_mean=[]
                for i in range(n_bins):
                    s=0
                    for j in range(k):
                        s+=list_mean[j][i]
                    sum_mean.append(s)
                    
                
                mean_indentation = [x / k for x in sum_mean]
                
                # Define a new force axis with a point in the middle of every bin 
                new_y=[i*bin_size/2 for i in range(1,2*n_bins,2)]
                new_y=np.array(new_y)
                
               
                # We define the first value of y axis to be the y coordinate of point of contact 
                new_y[0]=self.corrected_poc_y
                
                # We define the first value of x axis to be the x coordinate of point of contact 
                mean_indentation[0]=self.corrected_poc_x
                
                # We convert the mean indentation list in array and calculate the standard deviation to plot the error bars
                mean_indentation=np.array(mean_indentation)
                standard_deviation=np.std(mean_indentation)
     
                # Plot the error bars 
                pen1= pg.mkPen(color=(255, 0, 0), width=7)
                self.graphWidget.plot(mean_indentation-self.corrected_poc_x, new_y-self.corrected_poc_y, pen=pen1,symbol='o')
                error = pg.ErrorBarItem(x=mean_indentation-self.corrected_poc_x, y=new_y-self.corrected_poc_y, right=standard_deviation, left=standard_deviation, beam=10e-9)  
                self.graphWidget.addItem(error)  
                

    # Function used to collect datas needed to plot the force vs indentation
    def collectData(self):
        self.deflection_sensitivity = None # m/V
        # If None it will use the spring constant from the file
        self.spring_constant = None # N/m
        self.filemetadata = self.file.filemetadata
        self.closed_loop = self.filemetadata['z_closed_loop']   
        self.file_deflection_sensitivity = self.filemetadata['defl_sens_nmbyV'] #nm/V
        self.file_spring_constant = self.filemetadata['spring_const_Nbym'] #N/m
        self.height_channel = self.filemetadata['height_channel_key']

        if not self.deflection_sensitivity: self.deflection_sensitivity = self.file_deflection_sensitivity / 1e9 #m/V
        if not self.spring_constant: self.spring_constant = self.file_spring_constant

        self.curve_idx = 0
        self.force_curve = self.file.getcurve(self.curve_idx)
        self.extend_segments = self.force_curve.extend_segments
        self.pause_segments = self.force_curve.pause_segments
        self.modulation_segments = self.force_curve.modulation_segments
        self.retract_segments = self.force_curve.retract_segments
        self.force_curve_segments = self.force_curve.get_segments()
        first_exted_seg_id, self.first_ext_seg = self.extend_segments[0]
        self.first_ext_seg.preprocess_segment(self.deflection_sensitivity, self.height_channel)
        last_ret_seg_id, last_ret_seg = self.retract_segments[-1]
        last_ret_seg.preprocess_segment(self.deflection_sensitivity, self.height_channel)
        xzero = last_ret_seg.zheight[-1] # Maximum height
        self.first_ext_seg.zheight = xzero - self.first_ext_seg.zheight
        last_ret_seg.zheight = xzero - last_ret_seg.zheight
        app_height = self.first_ext_seg.zheight
        app_deflection = self.first_ext_seg.vdeflection
        ret_height = last_ret_seg.zheight
        ret_deflection = last_ret_seg.vdeflection
        
        # Get the coordinates of the point of contact 
        
        self.poc = get_poc_RoV_method(app_height, app_deflection, 350e-9)
        
        self.first_ext_seg.get_force_vs_indentation(self.poc, self.spring_constant)
        self.app_indentation, self.app_force = self.first_ext_seg.indentation, self.first_ext_seg.force
        
        max_force=max(self.app_force) 
        force_division=np.where(self.app_force>=max_force/4)
        new_len=force_division[0][0]
     
        new_app_indentation=self.app_indentation[0:new_len]
        new_app_force=self.app_force[0:new_len]
        
        def model_f(x,a,b):
            return a*x+b
        
        popt, pcov = curve_fit(model_f, new_app_indentation, new_app_force) 
        a_opt, b_opt = popt
        
        x_model = np.linspace(min(new_app_indentation), max(new_app_indentation), new_len)
        y_model = model_f(x_model, a_opt, b_opt)      
        
        minus_y=new_app_force-y_model  
        min_ind=minus_y.argmin()
        
        self.corrected_poc_x = self.app_indentation[min_ind]
        self.corrected_poc_y = self.app_force[min_ind]
        
        

    
    # Function used in the opening of a folder
    def getFileList(self, directory):
        types = ('*.jpk-force', '*.jpk-force-map', '*.jpk-qi-data', '*.jpk-force.zip', '*.jpk-force-map.zip', '*.jpk-qi-data.zip', '*.spm', '*.pfc')
        dataset_files = []
        for files in types:
            dataset_files.extend(glob.glob(f'{directory}/**/{files}', recursive=True))
        return dataset_files
  
    
    # Function used to read the .jpk-force files
    def loadfile(self, filepath):
        split_path = filepath.split(os.extsep)
        if os.name == 'nt' and split_path[-1] == '.zip':
            filesuffix = split_path[-2]
        else:
            filesuffix = split_path[-1]
    
        uffobj = UFF()
    
        if filesuffix[1:].isdigit() or filesuffix in nanoscfiles:
            return loadNANOSCfile(filepath, uffobj)
    
        elif filesuffix in jpkfiles:
            return loadJPKfile(filepath, uffobj, filesuffix)
        
        elif filesuffix in ufffiles:
            return loadUFFtxt(filepath, uffobj)
        
        elif filesuffix in jpkthermalfiles:
            return loadJPKThermalFile(filepath)

        
    # Function used to plot the deflection vs the height for a file
    def plot_data(self):
        
        # Recover all necessary data from the file
        self.deflection_sensitivity = None # m/V
        # If None it will use the spring constant from the file
        self.spring_constant = None # N/m
        self.filemetadata = self.file.filemetadata
        self.closed_loop = self.filemetadata['z_closed_loop']
        self.file_deflection_sensitivity = self.filemetadata['defl_sens_nmbyV'] #nm/V
        self.file_spring_constant = self.filemetadata['spring_const_Nbym'] #N/m
        self.height_channel = self.filemetadata['height_channel_key']
        if not self.deflection_sensitivity: self.deflection_sensitivity = self.file_deflection_sensitivity / 1e9 #m/V
        if not self.spring_constant: self.spring_constant = self.file_spring_constant

        self.curve_idx = 0
        self.force_curve = self.file.getcurve(self.curve_idx)
        self.extend_segments = self.force_curve.extend_segments
        self.pause_segments = self.force_curve.pause_segments
        self.modulation_segments = self.force_curve.modulation_segments
        self.retract_segments = self.force_curve.retract_segments
        self.force_curve_segments = self.force_curve.get_segments()
        
        # Define a graph
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget)
        self.graphWidget.setBackground('w')
        
        # Plot the curve
        colors = [ (0, 0, 255),(255, 128, 0)] # define orange and blue colors
        for i, (seg_id, segment) in enumerate(self.force_curve_segments):
            height = segment.segment_formated_data[self.height_channel]
            deflection = segment.segment_formated_data["vDeflection"]
            pen = pg.mkPen(color=colors[i%len(colors)], width=5) # set the color based on index
            self.graphWidget.plot(height, deflection, pen=pen)
        styles = {'color':'k', 'font-size':'20px'}
        self.graphWidget.setLabel('left', 'vDeflection [Volts]',**styles)
        self.graphWidget.setLabel('bottom', 'Piezo Height [Meters]',**styles)

        
    # Function used to plot the force vs the indentation for a folder 
    def plot_force(self):
        self.first_ext_seg.get_force_vs_indentation(self.poc, self.spring_constant)
        self.app_indentation, self.app_force = self.first_ext_seg.indentation, self.first_ext_seg.force
        
        # Plot the curves of every files on the same graph
        if not hasattr(self, 'graphWidget'):
            self.graphWidget = pg.PlotWidget()
            self.setCentralWidget(self.graphWidget)
            self.graphWidget.setBackground('w')
 
        pen = pg.mkPen(color=(0, 0, 255))
        self.graphWidget.plot(self.app_indentation-self.corrected_poc_x, self.app_force-self.corrected_poc_y, pen=pen)
        styles = {'color':'k', 'font-size':'20px'}   
        self.graphWidget.setLabel('left', 'Force [Newton]',**styles)
        self.graphWidget.setLabel('bottom', 'Indentation [Meters]',**styles)

    
    # Function used to plot and give the coordinates of the Point of Contact 
    def calculate_poc(self):
        
        # Recover all necessary data from the file
        self.deflection_sensitivity = None # m/V
        # If None it will use the spring constant from the file
        self.spring_constant = None # N/m
        self.filemetadata = self.file.filemetadata
        self.closed_loop = self.filemetadata['z_closed_loop']
        self.file_deflection_sensitivity = self.filemetadata['defl_sens_nmbyV'] #nm/V
        self.file_spring_constant = self.filemetadata['spring_const_Nbym'] #N/m
        self.height_channel = self.filemetadata['height_channel_key']
        if not self.deflection_sensitivity: self.deflection_sensitivity = self.file_deflection_sensitivity / 1e9 #m/V
        if not self.spring_constant: self.spring_constant = self.file_spring_constant

        self.curve_idx = 0
        self.force_curve = self.file.getcurve(self.curve_idx)
        self.extend_segments = self.force_curve.extend_segments
        self.pause_segments = self.force_curve.pause_segments
        self.modulation_segments = self.force_curve.modulation_segments
        self.retract_segments = self.force_curve.retract_segments
        self.force_curve_segments = self.force_curve.get_segments()
        first_exted_seg_id, self.first_ext_seg = self.extend_segments[0]
        self.first_ext_seg.preprocess_segment(self.deflection_sensitivity, self.height_channel)
        last_ret_seg_id, last_ret_seg = self.retract_segments[-1]
        last_ret_seg.preprocess_segment(self.deflection_sensitivity, self.height_channel)   
        xzero = last_ret_seg.zheight[-1] # Maximum height
        self.first_ext_seg.zheight = xzero - self.first_ext_seg.zheight
        last_ret_seg.zheight = xzero - last_ret_seg.zheight
        app_height = self.first_ext_seg.zheight
        app_deflection = self.first_ext_seg.vdeflection
        ret_height = last_ret_seg.zheight
        ret_deflection = last_ret_seg.vdeflection        
        self.poc = get_poc_RoV_method(app_height, app_deflection, 350e-9)

        # Recover the indentation data and force data from the file
        self.first_ext_seg.get_force_vs_indentation(self.poc, self.spring_constant)
        self.app_indentation, self.app_force = self.first_ext_seg.indentation, self.first_ext_seg.force
        
        # We only fit 1/4 of the max force from the file, no need to take all the points
        max_force=max(self.app_force) 
        force_division=np.where(self.app_force>=max_force/4)
        new_len=force_division[0][0]
        new_app_indentation=self.app_indentation[0:new_len]
        new_app_force=self.app_force[0:new_len]
        
        # Definition of the fit model, here an affine function
        def model_f(x,a,b):
            return a*x+b
        
        # We calculate a good approximation for both a and b parameters
        popt, pcov = curve_fit(model_f, new_app_indentation, new_app_force) 
        a_opt, b_opt = popt
        
        # These are the x axis and y axis for the fit 
        x_model = np.linspace(min(new_app_indentation), max(new_app_indentation), new_len)
        y_model = model_f(x_model, a_opt, b_opt)      
        
        # We calculate the subtraction between force and fit and take the minimum, which will give us the point of contact
        minus_y=new_app_force-y_model  
        min_ind=minus_y.argmin()
        
        # Here are the coordinates of the point of contact
        self.corrected_poc_x = self.app_indentation[min_ind]
        self.corrected_poc_y = self.app_force[min_ind]
        
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget) 
        self.graphWidget.setBackground('w')
        pen = pg.mkPen(color=(0, 0, 255),width=7)
        pen3 = pg.mkPen(color=(255, 0, 0),width=5)
        
        # We plot the new indentation and force axis which correspond to 1/4 of the max force 
        # + We plot a vertical and horizontal line to make the point of contact more visible
        self.graphWidget.plot(new_app_indentation, new_app_force, pen=pen)
        vLine=pg.InfiniteLine(pos=self.corrected_poc_x, angle=90, pen=pen3)
        self.graphWidget.addItem(vLine)
        hLine=pg.InfiniteLine(pos=self.corrected_poc_y, angle=0, pen=pen3)
        self.graphWidget.addItem(hLine)
        styles = {'color':'k', 'font-size':'20px'}   
        self.graphWidget.setLabel('left', 'Force [Newton]',**styles)
        self.graphWidget.setLabel('bottom', 'Indentation [Meters]',**styles)
    
        # Display point of contact coordinates
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Point of contact coordinates")
        dlg.setText("x: " + str(self.corrected_poc_x) + "meters" + ", y: " + str(self.corrected_poc_y) + "newtons")
        dlg.exec()        
      
     
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
