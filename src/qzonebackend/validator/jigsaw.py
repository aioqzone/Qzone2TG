import numpy as np
import urllib.request as request
import cv2 as cv

fromlocal = False

def read(url: str)-> np.ndarray:
    if fromlocal:
        return cv.imread(url, cv.IMREAD_UNCHANGED)
    else:
        res = request.urlopen(url)
        img = np.array(bytearray(res.read()), dtype=np.uint8)
        return cv.imdecode(img, -1)

def findDarkArea(fore_url, back_url, fore_rect, back_rect):
    fore_rect['x'] = round(fore_rect['x'] - back_rect['x'])
    fore_rect['y'] = round(fore_rect['y'] - back_rect['y'])

    fore_scale = 0.75
    fore = cv.resize(
        read(fore_url), 
        (round(fore_rect['width'] * fore_scale), round(fore_rect['height'] * fore_scale))
    )
    back = cv.resize(read(back_url), (back_rect['width'], back_rect['height']))
    _, mask = cv.threshold(fore[:, :, 3], 200, 255, cv.THRESH_BINARY)
    back = cv.cvtColor(back, cv.COLOR_BGR2GRAY)[
        fore_rect['y']: fore_rect['y'] + fore_rect['height'], 
        fore_rect['x'] + fore_rect['width']:
    ]
    wbias = back.shape[1] // 2
    back = back[:, wbias:]
    
    close = cv.morphologyEx(back, cv.MORPH_CLOSE, mask, iterations=1)
    u, d = close.max(), close.min()
    enhance = (255 * (1 - (close - d) / (u - d))).astype(np.uint8)
    _, final = cv.threshold(enhance, 250, 255, cv.THRESH_BINARY)
    
    cont, _ = cv.findContours(final, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE)
    cont = max(cont, key = cv.contourArea)
    rect = cv.boundingRect(cont)

    display = cv.cvtColor(back, cv.COLOR_GRAY2BGR)
    display = cv.rectangle(display, rect, (0, 0, 255))
    cv.imshow('close', close)
    cv.imshow('final', final)
    cv.imshow('display', display)
    cv.waitKey()
    D = fore_rect['width'] * (fore_scale / 2)
    return round(rect[0] + wbias + fore_rect['width'] - D), D

def contourMatch(fore_url, back_url, fore_rect, back_rect):
    fore = read(fore_url)
    back = read(back_url)

    fws = fore.shape[1] / fore_rect['width']
    fhs = fore.shape[0] / fore_rect['height']

    fore_rect['x'] = round((fore_rect['x'] - back_rect['x']) * fws)
    fore_rect['y'] = round((fore_rect['y'] - back_rect['y']) * fhs)

    _, mask = cv.threshold(fore[:, :, 3], 200, 255, cv.THRESH_BINARY)
    back = cv.cvtColor(back, cv.COLOR_BGR2GRAY)[
        fore_rect['y']: fore_rect['y'] + fore.shape[0], 
        fore_rect['x'] + fore.shape[1]:
    ]
    wbias = back.shape[1] // 2
    back = back[:, wbias:]

    _, backbin = cv.threshold(back, 110, 255, cv.THRESH_OTSU)
    backbin = cv.morphologyEx(backbin, cv.MORPH_CLOSE, cv.getStructuringElement(cv.MORPH_RECT, (3, 3)))

    back_canny = cv.Canny(backbin, 100, 200)
    display = cv.cvtColor(back_canny, cv.COLOR_GRAY2BGR)

    jcont, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE)
    jcont = max(jcont, key = cv.contourArea)
    pcont, hier = cv.findContours(255 - backbin, cv.RETR_TREE, cv.CHAIN_APPROX_NONE)
    pcont = min(pcont, key=lambda i: cv.matchShapes(i, jcont, 1, 0.))
    rect = cv.boundingRect(pcont)

    cv.drawContours(display, [pcont], 0, (0, 0 ,255))
    # for i in range(len(pcont)):
    #     display = cv.cvtColor(back_canny, cv.COLOR_GRAY2BGR)
    #     cv.drawContours(display, pcont, i, (0, 0 ,255))
    #     cv.imshow('display', display)
    #     cv.waitKey()

    cv.imshow('back', back)
    cv.imshow('back_canny', back_canny)
    cv.imshow('backbin', backbin)
    cv.imshow('display', display)
    cv.waitKey()

    D = fore_rect['width'] / 2
    return round((rect[0] + wbias + fore.shape[1] - D) / fws), round(D / fws)