from PIL import Image
from io import BytesIO

def get_image_difference(back_bytes, full_bytes):
    back_img = Image.open(BytesIO(back_bytes))
    full_img = Image.open(BytesIO(full_bytes))
    width, height = full_img.size

    for w in range(0, width):
        for h in range(0, height):
            back_pixel = back_img.getpixel((w, h))
            full_pixel = full_img.getpixel((w, h))

            if back_pixel != full_pixel and w > 340 and h > 10 and abs(back_pixel[0]-full_pixel[0])>50 and abs(back_pixel[1]-full_pixel[1])>50 and abs(back_pixel[2]-full_pixel[2])>50:
                return True, w

    return False, -1