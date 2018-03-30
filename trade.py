import hashlib
import hmac
import json
import logging
from cmath import sqrt
from time import time, sleep
from urllib.parse import urlencode
import requests

#パラメータ
KEY = ''
SECRET = ''
CURRENCY_PAIR = 'btc_jpy'
period = 20


last_price_list = []


# 現物取引API
def tradeRequester(params, key, secret):
    encoded_params = urlencode(params)
    signature = hmac.new(bytearray(secret.encode('utf-8')), digestmod=hashlib.sha512)
    signature.update(encoded_params.encode('utf-8'))

    headers = {
        'key': key,
        'sign': signature.hexdigest()
    }

    response = requests.post('https://api.zaif.jp/tapi', data=encoded_params, headers=headers)

    if response.status_code == 200:

        response_dict = json.loads(response.text)
        return response_dict
    else:
        raise Exception('status_code is {status_code}, params are {params}'.format(status_code = response.status_code, params = str(params)))


# サーバ時刻取得
def getTimestamp(key, secret):
    params = {
        'method': 'get_info2',
        'nonce': time()
    }
    response_dict = tradeRequester(params, key, secret)
    timestamp = response_dict['return']['server_time']
    return timestamp


# 現在価格取得
def getLastPrice():
    response = requests.get('https://api.zaif.jp/api/1/last_price/' + CURRENCY_PAIR)
    if response.status_code == 200:
        response_json = response.json()
        last_price = response_json['last_price']
        return last_price
    else:
        raise Exception('status_code is {status_code}, params are {params}', status_code = response.status_code, params = 'last_price')


# 残高取得
def getBalance(key, secret):
    params = {
        'method': 'get_info2',
        'nonce': time()
    }
    response_dict = tradeRequester(params, key, secret)
    jpy = response_dict['return']['funds']['jpy']
    btc = response_dict['return']['funds']['btc']
    return jpy, btc


# 移動平均線
def moving_ave(last_price, period):
    sum_price = 0
    for price in last_price[-period:]:
        sum_price += price
    return sum_price / period


# 標準偏差
def st_div(price, period):
    sum_price = 0
    sum_price_2 = 0
    for price in last_price_list[-period:]:
        sum_price += price
        sum_price_2 += price**2
    return sqrt((period*sum_price_2-sum_price**2)/period*(period-1))


##ログ取得設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('[%(levelname)s] %(asctime)s %(message)s')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logger.addHandler(stream_handler)

##時刻変数定義
current_timestamp = None
previous_timestamp = None

##ループカウンタ初期化
counter = 0

logger.info('準備完了')

while True:
    print(len(last_price_list))
    try:
        #ループ開始処理
        counter += 1
        logger.info('ラウンド{}開始'.format(counter))
        previous_timestamp = current_timestamp
        current_timestamp = getTimestamp(KEY, SECRET)
        order_price = getLastPrice()
        jpyBalance, btcBalance = getBalance(KEY, SECRET)
        last_price_list.append(order_price)
        logger.info('現在価格: {}'.format(last_price_list[-1]))
        buy_flag = False

        if len(last_price_list) >= period:
            m = moving_ave(last_price_list, period)
            b = m + st_div(last_price_list, period)

            if m > b and buy_flag == False:
                amount = round((jpyBalance / order_price), 4)
                params = {
                    'method': 'trade',
                    'nonce': time(),
                    'currency_pair': CURRENCY_PAIR,
                    'action': 'ask',
                    'price': order_price,
                    'amount': amount,
                }
                response_dict = tradeRequester(params, KEY, SECRET)

                if response_dict['success'] == 1:
                    buy_flag = True
                    logger.info('買い発注({})'.format(order_price))
                elif response_dict["success"] == 0:
                    logger.warning('買い発注失敗: {} '.format(response_dict['error']))

            if m < b and buy_flag == True:
                amount = btcBalance
                params = {
                    'method': 'trade',
                    'nonce': time(),
                    'currency_pair': CURRENCY_PAIR,
                    'action': 'bid',
                    'price': order_price,
                    'amount': amount,
                }
                response_dict = tradeRequester(params, KEY, SECRET)

                if response_dict['success'] == 1:
                    buy_flag = True
                    logger.info('売り発注({})'.format(order_price))
                elif response_dict["success"] == 0:
                    logger.warning('売り発注失敗: {} '.format(response_dict['error']))


        logger.info('ラウンド{}終了'.format(counter))
        logger.info('60秒後に次ラウンド開始\n')

        # ラウンド完了後、60秒待つ
        sleep(60)

    except Exception as e:
        assert isinstance(logger, object)
        logger.warning('取引ループ中にエラー発生、60秒待機:  %r\n' % e)
        sleep(60)
