
################################################
### Modified 1/1/2019, Dalton Tinoco
### Cosmic watch signal import script
###
### Entry point: import headers here
### Removed imports:
### import numpy as np : Unused
### import json : Unused
################################################
import threading as TH        # For threading functionality for workers
import msvcrt
import serial
import math
import time
import glob
import sys
import signal
import logging
import codecs
import numpy as np
import matplotlib
import array

matplotlib.use("TkAgg")
import pylab
pylab.ion()
    
from datetime import datetime
from multiprocessing import Process

MAX_ARRAY_SIZE = 25

class ring_buffer:
    def __init__(self):
        self.data_buffer = array.array('f', np.zeros(MAX_ARRAY_SIZE))
        self.cur_index = 0

    def push_data(self, in_data):
        if self.cur_index == 0: # if index position is at head, overwrite head
            self.data_buffer[0] = in_data
            self.cur_index += 1
        elif self.cur_index < MAX_ARRAY_SIZE: # else if index position is between head and tail (inclusive)
            self.data_buffer[self.cur_index] = in_data # write data to index position
            if self.cur_index == (MAX_ARRAY_SIZE - 1): # if index position is tail, set index to head
                self.cur_index = 0
            else: # else increment by 1
                self.cur_index += 1

    ################################################
    ### Data Collection Worker Function
    ### Responsible for reading signal data from a
    ### USB port, and writing it to a file.
    ###
    ### CHANGES:
    ### removed signal handler, not nessecary for
    ### opening and closing files or opening COMS
    ################################################
def DataCollection(ArduinoPort, fname, id, exitflag, semi):
    try:
        ComPort = serial.Serial(port_list[int(ArduinoPort) - 1]) # open the COM Port
        ComPort.baudrate = 9600          # set Baud rate
        ComPort.bytesize = 8             # Number of data bits = 8
        ComPort.parity = 'N'           # No parity
        ComPort.stopbits = 1    
        print("Opening file...\n")

        my_file = open(fname, mode='w', newline="\n")
        #my_file = open(fname, "wb", 0)

        counter = 0
        #file.write(str(datetime.now())+ " " + data)
        
        write_to_file = "Detection start time: " + str(datetime.now()) + "\n"
        print(write_to_file)
        my_file.write(write_to_file)
        write_to_file = ' '
        stats_buffer = ring_buffer()
        x = np.linspace(1, 25, 25)
        while True:
            if exitflag.locked():
                data = str((ComPort.readline()).decode())   # Wait and read data
                write_to_file = str(datetime.now()) + " : " + data
                my_file.write(write_to_file)
                #add data to stats buffer
                stats_buffer.push_data(float(data.split()[3]))
                print("Mean: " + str(np.mean(stats_buffer.data_buffer)) + ", Std: " + str(np.std(stats_buffer.data_buffer)), end='\r')
                semi.acquire()
                time.sleep(0.025)
                semi.release()
            else:
                break

        print("Shutting down open files and ports...\n")
        ComPort.close()     
        #my_file.write("#") # end of file marker
        my_file.close()
        return True
    except Exception as e:
        print(e)
        print("An error occured... Beats me what it is but it sucks!")
    return True
    
def detection(semi, exitflag):
    filename = "Detection_list.txt"
    counter = 0
    lock_counter = 0
    my_file = open(filename, mode='w', newline="\n")
    print("starting detection...\n")
    while exitflag.locked():
        for s in semi:
            if s.locked():
                lock_counter += 1
        lock_counter = 0
        if lock_counter >= 2:
            counter += 1
            my_file.write(str(counter) + " " + str(datetime.now()))
        time.sleep(0.00125)
    my_file.close()


################################################
### Thread Container Class
### Responsible for managing thread pool and
### destruction/garbage
###
### CHANGES:
### ADDED: __exit__ method so calls to sys.exit()
### invoke destruction of class instance.
################################################
class ThreadContainer:
    def __init__(self):
    #Member Variables init.
        self.threadpool = []
        self.FileNames = []
        self.lo = TH._allocate_lock()
        self.bank = []

    def start_threads(self, AvailablePorts, NamesList):
    # Starts worker threads to collect data
        self.lo.acquire(False)
        for j in range(0, len(AvailablePorts)):
            self.bank.append(TH._allocate_lock())
        for i in range(0, len(AvailablePorts)):
            print("Starting thread, file: " + NamesList[i] + " Port: " + str(AvailablePorts[i]) + "\n")
            t = TH.Thread(target=DataCollection, args=(AvailablePorts[i], NamesList[i], i, self.lo, self.bank[i]))
            self.threadpool.append(t)
            t.start()

        t = TH.Thread(target=detection, args=(self.bank, self.lo))
        self.threadpool.append(t)
        t.start()


    def stop_workers(self):
        self.lo.release()
        for t in self.threadpool:
            t.join()    

class sync_lock:
    def __enter__(self):
    # with constructor
        self.exitlock = TH.Lock()
        print("\\nAcquired Lock" + str(datetime.now()) + '\n')
        return self.exitlock

    def __exit__(self, exc_type, exc_value, tb):
        self.exitlock.release() # release lock, telling threads to stop 
        print("\nReleased Lock" + str(datetime.now()) + '\n')

################################################
### Lists serial port names
###    :raises EnvironmentError On unsupported or unknown platforms
###    :returns A list of the serial ports available on the system
################################################

def serial_ports():
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')
        sys.exit(0)
    result = []
    i = 1
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
            print("Port " + str(i) + " Open\n")
        except (OSError, serial.SerialException):
            pass
        i += 1
    return result

############################################
###     This file is used to save real-time data from the detector.  You will
###     have to change
###     the variable ComPort to the name of the USB port it is plugged into.
###     If the Arduino
###     is not recognized by your computer, make sure you haveinstalled the
###     drivers for the Arduino.
###############################################

collector = ThreadContainer()
print('\n             Welcome to:   ')
print('CosmicWatch: The Desktop Muon Detector\n')

Port_Map = []
port_list = serial_ports() #list available ports to collect from
size_pl = len(port_list)
print(size_pl)
if size_pl > 0:
    print('Available serial ports:\n')
    for i in range(0,len(port_list)):
        print('[' + str(i + 1) + '] ' + str(port_list[i]))
    print('[h] help\n')
    #PYTHON2.7 input -> raw_input
    print("Select Arduino Ports, seperate with space (eg. 0 1):\n")
    Port_Map = list(map(int, input().split()))
else :
    Port_Map = list(range(0,len(port_list))) # set default ports to comm1 and comm2
    print("The selected ports are:")
    for i in range(0,len(Port_Map)):
        print(str(Port_Map[i]) + ' ')
    print('\n')
print("Enter file names seperated by a space (eg. <PATH>/test_sensor1.txt <PATH>/test_sensor2.txt)\n")
FileNameList = list(input().split())
print("Taking data ...")
print("Press q to stop: ")

collector.start_threads(Port_Map, FileNameList)
interupt_key = ' '

x = np.linspace(0, 100, 100)
y = np.linspace(0, 100, 100)

while True: # keyboard driven inturrupt loop
    interupt_key = input()
    if interupt_key == 'q':
        print("shutting down detection")
        collector.stop_workers()
        break
    elif interupt_key == 's':
        matplotlib.pylab.scatter(x, y)
        matplotlib.pylab.show()
    else:
        print("not a command.\n")
        pass
interupt_key = input("\n\nLoad file for plotting? y/n: ")
if interupt_key == 'y':
    f_line_in = " "
    my_files = []
    ln = 0
    count = 0
    data_buff = []
    for fname in collector.FileNames:
        data_buff.append(array.array('f'))
        with open(fname, mode='r') as fp:
            for f_line_in in enumerate(fp):
                if ln == 0:
                    ln += 1
                    pass
                else:
                    data_buff[count].append(float(f_line_in.split()[6]))
                count += 1
        # display stats about files
    for arr in data_buff:
        dat_mean = str(np.mean(arr))
        dat_stdd = str(np.std(arr))
        print("Statisticts stuff:\n")
        print("Mean = {}, Standard Deviation = {}\n\n".format(dat_mean, dat_stdd))
