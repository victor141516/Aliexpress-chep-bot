import logging
import os
from random import randint, shuffle
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

USERNAME = os.environ.get('USERNAME')
PASSWORD = os.environ.get('PASSWORD')
CC_MONTH = os.environ.get('CC_MONTH')
CC_YEAR = os.environ.get('CC_YEAR')
CREDIT_CARD_EXPIRATION = {'month': CC_MONTH, 'year': CC_YEAR}


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s')
ch.setFormatter(formatter)
LOGGER.addHandler(ch)


class Alibot(object):
    def __init__(self, remote_worker=None, username=None, password=None, max_price=None, credit_card_expiration=None):
        super(Alibot, self).__init__()
        if (remote_worker):
            self._browser = webdriver.Remote(
                command_executor=remote_worker,
                desired_capabilities=DesiredCapabilities.CHROME)
        else:
            self._browser = webdriver.Chrome()
        self.username = username
        self.password = password
        self.max_price = max_price
        self.credit_card_expiration = credit_card_expiration

    def __del__(self):
        try:
            self._browser.quit()
        except:
            pass

    def _browser_wait_for_element_by_xpath(self, xpath, timeout=10):
        return WebDriverWait(self._browser, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )

    def _browser_wait_for_element_and_click(self, xpath, timeout=10):
        element = self._browser_wait_for_element_by_xpath(xpath, timeout)
        element.click()
        return element

    def _browser_wait_for_element_and_send_keys(self, xpath, keys, timeout=10):
        element = self._browser_wait_for_element_by_xpath(xpath, timeout)
        element.send_keys(keys)
        return element

    def _browser_wait_for_url(self, regex):
        pattern = re.compile(regex)
        for i in range(0, 20):
            if (pattern.match(self._browser.current_url)):
                return True
            else:
                time.sleep(0.5)

    def login(self, username=None, password=None):
        LOGGER.info('Login begins')
        self.username = username or self.username
        self.password = password or self.password
        self._browser.get('https://login.aliexpress.com/')
        self._browser.switch_to_frame(self._browser.find_element_by_id('alibaba-login-box'))
        username_input = self._browser.find_element_by_id('fm-login-id')
        password_input = self._browser.find_element_by_id('fm-login-password')
        submit_button = self._browser.find_element_by_id('login-submit')
        time.sleep(1)
        username_input.send_keys(username)
        password_input.send_keys(password)
        submit_button.click()
        LOGGER.info('Login form sent')
        self._browser_wait_for_url('https:\/\/(www|[a-z][a-z])\.aliexpress\.com\/')
        return len(self._browser.find_element_by_xpath('//*[@data-role="signout-btn"]/a').get_attribute('href').split('xlogout.htm')[1]) > 0  # This happens when log in is successful

    def get_cheap_thing(self, max_price=None):
        self.max_price = max_price or self.max_price
        getter_url = 'http://www.1dollarthings.com/aliexpress/{price}?page={page}&category={category}'.format(
                        price=int(self.max_price),
                        page=randint(1, 100),
                        category=randint(1, 19))

        cheap_stuff = requests.get(getter_url).json()

        try:
            cheap_stuff = cheap_stuff['data']['result']['products']
        except:
            return self.get_cheap_thing(max_price)
        if (len(cheap_stuff) < 1):
            return self.get_cheap_thing(max_price)

        shuffle(cheap_stuff)
        tries = 0
        while(float(cheap_stuff[0]['salePrice'][4:]) > max_price):
            tries += 1
            if (tries > 10):
                return self.get_cheap_thing(max_price)
            shuffle(cheap_stuff)
        return {
            'name': cheap_stuff[0]['productTitle'],
            'link': cheap_stuff[0]['productUrl'],
            'price': float(cheap_stuff[0]['salePrice'][4:])
        }

    def buy_thing(self, link, credit_card_expiration=None):
        self._browser.get(link)

        try:
            LOGGER.info('Trying to remove popup')
            self._browser_wait_for_element_and_click('//a[contains(@class, "close-layer")]', 3)
            time.sleep(2)
        except:
            LOGGER.info('No popup detected')
            pass

        options = self._browser.find_elements_by_xpath('//*[@id="j-product-info-sku"]/dl')
        for option in options:
            elements = option.find_elements_by_xpath('dd/ul/li/a')
            shuffle(elements)
            elements[0].click()
        LOGGER.info('Product options chosen')

        price_element = self._browser.find_element_by_id('j-total-price-value')
        price = float(price_element.text[2:].replace(',', '.'))

        if (price > self.max_price):
            LOGGER.error('Overprice')
            return 0  # Gastos de envio
        else:
            LOGGER.info('Price is fine')

        self._browser.find_element_by_id('j-buy-now-btn').click()
        try:
            self._browser_wait_for_element_by_xpath('//*[@id="captcha-image"]')
            LOGGER.error('Captcha detected')
            return 1  # Captcha
        except:
            LOGGER.info('No captcha detected')


        self._browser_wait_for_element_and_click('//*[@id="place-order-btn"]', 60)
        LOGGER.info('Buy button pressed')

        # Si pide fecha de caducidad de la tarjeta
        self._browser.switch_to_frame(self._browser_wait_for_element_by_xpath('//*[@id="j-isecurity-container"]/iframe'))
        LOGGER.info('iframe detected')
        is_credit_card_expiration = 1 == len(self._browser.find_elements_by_xpath('//div[contains(@class, "ui-form-item-card-expire")]'))
        if (is_credit_card_expiration):
            LOGGER.info('Credit card validation')
            self._browser.find_element_by_id('cardMonth').send_keys(credit_card_expiration['month'])
            self._browser.find_element_by_id('cardYear').send_keys(credit_card_expiration['year'])
            self._browser.find_element_by_id('submitBtn').click()
        else:
            LOGGER.error('No credit card validation detected')
            return 2  # Si hay un iframe pero no es de confimacion de tarjeta

        LOGGER.info('Waiting purchase confimation')
        time.sleep(30)
        purchase_success = 1 == len(self._browser.find_elements_by_xpath('//div[contains(@class, "ui-feedback-success")]'))
        return purchase_success


LOGGER.info('Start')
if (os.environ.get('PWD', False) == '/app'):
    bot = Alibot('http://selenium-server:4444/wd/hub')
else:
    bot = Alibot()

if (bot.login(USERNAME, PASSWORD)):
    LOGGER.info('Login successful')
else:
    LOGGER.error('Login failed')

LOGGER.info('Getting cheap thing')
cheap_thing = bot.get_cheap_thing(1)
LOGGER.info('Got cheap thing')

LOGGER.info('Begin purchase')
purchase_success = bot.buy_thing(cheap_thing['link'], CREDIT_CARD_EXPIRATION)
while (purchase_success is not True):
    LOGGER.error('Purchase failed, retry')
    purchase_success = bot.buy_thing(cheap_thing['link'], CREDIT_CARD_EXPIRATION)
    cheap_thing = bot.get_cheap_thing(1)
    LOGGER.error('Error code: {}'.format(purchase_success))

LOGGER.info('Purchase success')
LOGGER.info(cheap_thing)

#     Errores
# 0 - Gastos de envio
# 1 - Captcha
# 2 - No pide confirmar tarketa
