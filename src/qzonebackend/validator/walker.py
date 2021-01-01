import logging
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from .jigsaw import findDarkArea, contourMatch

logger = logging.getLogger("Selenium Walker")

class Walker:
    getDriver = webdriver.Edge
    crackMethod = contourMatch

    def __init__(self, refresh_time=10, *driver_args, **driver_kwargs):
        self.refresh_time = refresh_time

        # chrome_options = Options()
        # if self.headless: chrome_options.add_argument('--headless')
        
        # chrome_options.add_argument("log-level=%d" % self.log_level)
        self.driver = self.getDriver(*driver_args, **driver_kwargs)

    def login(self, uin, pwd):
        
        self.switchFrame(uin, pwd)
        for i in range(self.refresh_time):
            if i > 0: logger.info('第%d次尝试登陆' % (i + 1))
            cookie = self.crackValidate(self.driver)
            if cookie: return cookie

    def switchFrame(self, uin, pwd):
        logger.info("等待登陆界面加载")
        self.driver.get('https://qzone.qq.com/')
        logger.info("登陆界面加载完成")

        self.driver.switch_to.frame('login_frame')

        self.driver.find_element_by_id('switcher_plogin').click()
        self.driver.find_element_by_id('u').clear()
        self.driver.find_element_by_id('u').send_keys(uin)
        self.driver.find_element_by_id('p').clear()
        self.driver.find_element_by_id('p').send_keys(pwd)
        self.driver.find_element_by_id('login_button').click()

        try: WebDriverWait(self.driver, 3).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, 'tcaptcha_iframe'))
        )
        except TimeoutException:
            # TODO
            raise RuntimeError('限制登陆.')
        
    def crackValidate(self, uin):
        WebDriverWait(self.driver, 3).until(lambda dr: dr.find_element_by_id('slideBg').get_attribute('src'))
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

        w, D = contourMatch(fore_url, back_url, fore_rect, back_rect)
        if w <= 0:
            refresh.click()
            return
        
        for i, xoff in enumerate([w, w + D, w - D]):
            ac = ActionChains(self.driver)
            ac.click_and_hold(thumb)
            ac.move_by_offset(xoffset=xoff, yoffset=0)
            ac.release(thumb)
            ac.perform()
            
            cur_url = self.driver.current_url

            logger.info('又' * i + "等待跳转至Qzone")
            try: WebDriverWait(self.driver, 2).until(lambda dr: "请控制拼图块对齐缺口" in guide.text)   # 找错误提示
            except NoSuchElementException: pass                             # 没找到说明有可能过了
            else: continue

            try: WebDriverWait(self.driver, 5, 0.5).until(
                lambda dr: cur_url != self.driver.current_url
            )
            except NoSuchElementException: continue                         # 网页没变, 重来
            else: 
                if ("user.qzone.qq.com/" + uin) in self.driver.current_url: break
                else: raise RuntimeError('穿越到未知的地界... ' + self.driver.current_url)
        else: return

        logger.info('跳转成功 (成功混过验证')
        cookie = self.driver.get_cookies()
        qzonetoken = self.driver.execute_script('return window.g_qzonetoken')

        self.driver.close()
        self.driver.quit()

        cookie = {i["name"]: i["value"] for i in cookie}
        cookie["qzonetoken"] = qzonetoken

        return cookie