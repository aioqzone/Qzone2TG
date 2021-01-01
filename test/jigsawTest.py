import unittest
from qzonebackend.validator.jigsaw import findDarkArea, contourMatch

class JigsawTest(unittest.TestCase):
    def testFindDarkness(self):
        w, d = findDarkArea(
            'E:/Downloads/hycdn.png', 
            'E:/Downloads/hycdn.jfif', 
            {'height': 55, 'width': 55, 'x': 31.99236488342285, 'y': 35.18701934814453}, 
            {'height': 160, 'width': 280, 'x': 9.996182441711426, 'y': 23.187021255493164}
        )
        print(w)

    def testContourMatch(self):
        w, d = contourMatch(
            'E:/Downloads/hycdn.png', 
            'E:/Downloads/hycdn.jfif', 
            {'height': 55, 'width': 55, 'x': 31.99236488342285, 'y': 35.18701934814453}, 
            {'height': 160, 'width': 280, 'x': 9.996182441711426, 'y': 23.187021255493164}
        )
        print(w)