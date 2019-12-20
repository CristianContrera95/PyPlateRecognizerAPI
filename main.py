import os
import sys
import re
import time
import pickle
import configparser
import json
from multiprocessing import Process, Queue
from datetime import datetime as dt

import numpy as np
import cv2
from PIL import Image

from utils import FTP, API, CarDetector


CONFIG_FILE = 'config.ini'
VERSION = '0.1'

queue = Queue()


def put_file_in_queue(ftp):
    global queue
    images_processed = []
    while True:
        ftp_files = ftp.get_files_from_folder(ftp.folder)
        ftp_files = list(sorted(filter(lambda x: x.startswith('Patente'), ftp_files)))[:5]
        images = []
        for ftp_file in ftp_files:
            if ftp_files in images_processed: continue
            if not ftp.get_file(ftp_file):
                continue
            imagen = ftp.img_buff.getvalue()
            #ftp.ftp.delete(ftp.folder+'/'+ftp_file)
            images_processed.append(ftp_file)
            images.append((imagen, ftp_file))
        if images:
            queue.put(images)

        time.sleep(1000)


def get_file_in_queue():
    global queue
    if not queue.empty():
        return queue.get()
    return []


def cut_and_save(car_image_path, plate_box, plate, plates_folder):
    # img_plate = cv2.imread(car_image_path)
    #y1, x1, y2, x2 = plate_box  # ymin, xmin, ymax, xmax
    #img_plate = img_plate[y1:y2, x1:x2]
    #cv2.imwrite(os.path.join(plates_folder, plate+'.jpg'), img_plate)
    img_plate = Image.open(car_image_path)
    img_plate = img_plate.crop(tuple(plate_box))
    img_plate.save(os.path.join(plates_folder, plate+'.jpg'))
    return img_plate


def main():
    global queue

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if (not config) or (not config.sections()):
        print('No se encontro el archivo de configuracion.')
        exit(0)

    ftp_images_folder = config['folders'].get('ftp_images', '')
    car_images_folder = config['folders'].get('car_images', '.')
    plates_folder = config['folders'].get('plates', '.')

    ftp = FTP(url=config['ftp'].get('server_url'),
              port=int(config['ftp'].get('server_port', '9999')),
              folder=config['ftp'].get('server_folder', '.'),
              user=config['ftp'].get('user', 'anonymous'),
              password=config['ftp'].get('password', '')
              )
    if ftp.connect():
        exit(0)
    if ftp.login():
        exit(0)
    #ftp.change_folder()

    api = API(api_url=config['api'].get('API_URL', ''),
              token=config['api'].get('API_TOKEN', ''),
              )

    car_detector = CarDetector(model=config['car_detect'].get('model'),
                               threshold=int(config['car_detect'].get('threshold', '50')),
                               )

    proc_put_file = Process(target=put_file_in_queue, 
                            args=(ftp,)
                            )

    proc_put_file.start()
    print('Ready and working..\n')
    with open('plates_result_{}.json'.format(dt.now().strftime('%Y-%m-%d')), 'a') as fp:
        fp.write('[\n')

        while True:
            images = get_file_in_queue()
            if not images:
                time.sleep(1)
                continue
            images_list = []

            for image, image_name in images:
                img = np.frombuffer(image, dtype=np.uint8)
                img = cv2.imdecode(img, 1)
                if ftp_images_folder:
                    cv2.imwrite(os.path.join(ftp_images_folder, image_name), img)
                images_list.append(img)
            car_images = car_detector.detect(images_list)

            for car_image in car_images:
                car_image_path = os.path.join(car_images_folder, 'car_'+str(len(os.listdir(car_images_folder)))+'.jpg')
                if not cv2.imwrite(car_image_path, car_image[4]):
                    print('No se pudo guardar la imagen en {}'.format(car_image_path))
                    continue

                response = api.request(car_image_path)
                result = response['results']

                plate, plate_box = api.improve_plate(result)

                img_plate = cut_and_save(car_image_path, plate_box, plate, plates_folder)
                print('Plate detected: {}'.format(plate))
                #fp.write(str(dict(plate=plate, image_str=img_plate.tostring())))
            images = []
        fp.write(']')


if __name__ == '__main__':
    main()