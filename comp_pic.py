import numpy as np
import cv2 as cv

def read(url: str)-> np.ndarray:
    cap = cv.VideoCapture(url)
    if not cap.isOpened(): raise RuntimeError("url not opened")
    return cap.read()[1]
    
def get_image_difference(back_url, full_url):
    back = cv.cvtColor(read(back_url), cv.COLOR_BGR2GRAY)
    full = cv.cvtColor(read(full_url), cv.COLOR_BGR2GRAY)

    d = full - back
    cont, hier = cv.findContours(d[10:,340:], cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE)

    cont = max(cont, key = cv.contourArea)
    rect = cv.boundingRect(cont)

    return rect[0] + 340