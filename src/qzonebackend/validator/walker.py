import logging
import os

from selenium.common.exceptions import (
    NoSuchElementException, StaleElementReferenceException, TimeoutException
)
from selenium.webdriver import *
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .jigsaw import contourMatch, findDarkArea
from time import time

logger = logging.getLogger("Selenium Walker")


class Walker:
    crackMethod = contourMatch
    qr_url_callback = None
    driver: Edge

    def __init__(
        self,
        browser='Chrome',
        driver={},
        option=[],
        refresh_time=10,
        qr_strategy='prefer'
    ):
        self.refresh_time = refresh_time
        self.qr_strategy = qr_strategy

        # chrome_options = Options()
        # if self.headless: chrome_options.add_argument('--headless')
        # chrome_options.add_argument("log-level=%d" % self.log_level)
        if option:
            op = {
                'Firefox': FirefoxOptions,
                'Chrome': ChromeOptions,
                'IE': IeOptions,
            }[browser]()
            for i in option:
                op.add_argument('--' + i)
            driver[browser.lower() + '_options'] = op

        self.driver = {
            'Chrome': Chrome,
            'Firefox': Firefox,
            'Edge': Edge,
            'IE': Ie,
        }[browser](**driver)

    def register_qr_callback(self, qr_url_callback: callable):
        self.qr_url_callback = qr_url_callback

    def qrLogin(self, uin):
        """login with qrcode

        Args:
            uin (int): qq

        Returns:
            bool: if success
        """
        assert self.qr_url_callback, 'callback must not be None'

        cur_url = self.driver.current_url
        for i in range(self.refresh_time):
            os.makedirs('tmp/qrcode', exist_ok=True)
            qrpath = f'tmp/qrcode/{int(time())}.png'
            self.driver.find_element_by_id('qrlogin_img').screenshot(qrpath)
            self.qr_url_callback(qrpath)
            if self._waitForJump(cur_url, uin, timeout=120, poll_freq=2):
                logger.info('QR login success')
                return True
            logger.info(f'QR login failed # {i + 1}')
        os.removedirs('tmp/qrcode')
        return False

    def login(self, uin, pwd=None):
        """An adapter of qr-login and pwd-login.

        Args:
            uin (str): [description]
            pwd (str, optional): [description]. Defaults to None.
            qrcode (str, optional): `forbid`, `allow`, `prefer`, `force`. Defaults to 'forbid'.
            QRFetched (callable[str -> None], optional): What to do on QR url is fetched. Defaults to None.

        Raises:
            ValueError: if `qrcode` is illegal.

        Returns:
            str: cookie
        """
        logger.info("等待登陆界面加载")
        self.driver.get('https://qzone.qq.com/')
        logger.info("登陆界面加载完成")
        self.driver.switch_to.frame('login_frame')

        if self.qr_strategy == 'force':
            self.qrLogin(uin)

        elif self.qr_strategy == 'prefer':
            if not self.qrLogin(uin):
                self.driver.refresh()
                self.pwdLogin(uin, pwd)

        elif self.qr_strategy == 'allow':
            if not self.pwdLogin(uin, pwd):
                self.driver.refresh()
                self.qrLogin(uin)

        elif self.qr_strategy == 'forbid':
            self.pwdLogin(uin, pwd)

        else:
            self.driver.close()
            self.driver.quit()
            raise ValueError(self.qr_strategy)

        cookie = self._getCookie()
        self.driver.close()
        self.driver.quit()
        return cookie

    def pwdLogin(self, uin, pwd):
        self._switchFrame(uin, pwd)
        for i in range(self.refresh_time):
            if i > 0: logger.info('第%d次尝试登陆' % (i + 1))
            if self._crackValidate(uin): return True
        return False

    def _switchFrame(self, uin, pwd):
        self.driver.find_element_by_id('switcher_plogin').click()
        self.driver.find_element_by_id('u').clear()
        self.driver.find_element_by_id('u').send_keys(uin)
        self.driver.find_element_by_id('p').clear()
        self.driver.find_element_by_id('p').send_keys(pwd)
        self.driver.find_element_by_id('login_button').click()

        try:
            WebDriverWait(self.driver, 3).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, 'tcaptcha_iframe'))
            )
        except TimeoutException:
            # TODO 可能是要输入验证码?
            raise RuntimeError('限制登陆.')

    def _waitForJump(self, cur_url, uin, timeout=5, poll_freq=.5):
        try:
            WebDriverWait(self.driver, timeout, poll_freq
                          ).until(lambda dr: cur_url != self.driver.current_url)
        except (NoSuchElementException, TimeoutException):
            return False   # 网页没变, 重来
        else:
            if f"user.qzone.qq.com/{uin}" in self.driver.current_url: return True
            else: raise RuntimeError('穿越到未知的地界... ' + self.driver.current_url)

    def _getCookie(self):
        cookie = self.driver.get_cookies()
        qzonetoken = self.driver.execute_script('return window.g_qzonetoken')
        cookie = {i["name"]: i["value"] for i in cookie}
        cookie["qzonetoken"] = qzonetoken
        return cookie

    def _crackValidate(self, uin):
        try:
            WebDriverWait(
                self.driver, 5
            ).until(lambda dr: dr.find_element_by_id('slideBg').get_attribute('src'))
        except TimeoutException:
            logger.error('未找到captcha.')
            return False

        bg = self.driver.find_element_by_id('slideBg')
        jigsaw = self.driver.find_element_by_id("slideBlock")
        refresh = self.driver.find_element_by_id('e_reload')
        thumb = self.driver.find_element_by_id('tcaptcha_drag_thumb')
        guide = self.driver.find_element_by_id('guideText')

        back_url = bg.get_attribute('src')
        fore_url = jigsaw.get_attribute('src')

        WebDriverWait(self.driver, 3).until(lambda dr: jigsaw.rect['x'] > 0)
        back_rect = bg.rect
        fore_rect = jigsaw.rect

        print(fore_rect, back_rect, sep='\n')  # collecting test data
        w, D = contourMatch(fore_url, back_url, fore_rect, back_rect)
        if w <= 0:
            refresh.click()
            return False

        for i, xoff in enumerate([w, w + D, w - D]):
            ac = ActionChains(self.driver)
            ac.click_and_hold(thumb)
            ac.move_by_offset(xoffset=xoff, yoffset=0)
            ac.release(thumb)
            ac.perform()

            cur_url = self.driver.current_url

            logger.info('又' * i + "等待跳转至Qzone")
            try:
                WebDriverWait(self.driver,
                              2).until(lambda dr: "请控制拼图块对齐缺口" in guide.text) # 找错误提示
            except (TimeoutException, StaleElementReferenceException):
                pass                                                          # 没找到说明有可能过了
            else:
                continue

            if self._waitForJump(cur_url, uin): break
            else: continue

        else: return False

        logger.info('跳转成功 (成功混过验证')
        return True
