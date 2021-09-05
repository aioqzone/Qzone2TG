from time import time
import pytest

import demjson
from jssupport.jsjson import json_loads

js = '{htdocsPath:"https://captcha.gtimg.com/1",lang: "1",color:"007aff",tdcHtdocsPath:"",dcFileName:"tdx.js?app_data=6830346289576951808&t=2087065318?t=1628481457",vmFileName:"",noheader:"1",showtype:"embed",theme:"",uid:"",subcapclass:"",aid:"",uip:"2409:8a15:9226:b220::2",clientype:"",websig:"",collectdata:"collect",asig:"",buid:"",vmData:"",vsig:"",dst:"",nonce:"eda1152f11f1daf0",capSrc:"capFrame",spt:"75",curenv:"inner",fwidth:"",slink:"",sess:"s0nx3YK4QatvhJrQDGRgTQdIkelBWGiVmLpVtdQDMGHhd3IZwAJpbUKQ8_3ZsK8OsPp-SSGv9o-dxtA38qnXeY409iCroGUaf7pZK-geowA1b2u8sPhUJQpJZb4kDnHo_jzpe7FZIh0sJXlxn3-nAZOOIfT9Ge5DrttrYzgaDx5WCBuSm-qSEN-Ne8Ty8DMYM61pUD2XtzUQ16D5Z3yJly-GJXLPgXQxZzsVJnBT8MiIzh-wGh7nh-iFln5SZ4-r-Xpdv11i3U26Qv8TQcs2W2Wxl1k_-vFKono_G99ppojjRATWa9htQ0CQ**",cdnPic1:"/hycdn?index=1&image=937191257216919552",cdnPic2:"/hycdn?index=2&image=937191257216919552",iscdn:"1",vmByteCode:"",vmAvailable:"",TuCao:"https://support.qq.com/products/2136",ticket:"",randstr:"",powCfg:{md5:"403208f9b1cc81c1894740082126c761",prefix:"292186590b710e36"}}'


class TestAcc:
    def testAcc(self):
        m = json_loads(js)
        d = demjson.decode(js)
        assert set(m.keys()) == set(d.keys())

    def testExc(self):
        with pytest.raises(SyntaxError):
            json_loads(js.replace('}', '', 1))
        with pytest.raises(SyntaxError):
            json_loads(js.replace('"', '', 1))


class TestSpeed:
    # testDemjson (demjsonTest.TestSpeed) ... 1.7905035018920898 s
    # ok
    # testRegulate (demjsonTest.TestSpeed) ... 0.011957883834838867 s
    # ok
    def testDemjson(self):
        t = time()
        assert demjson.decode(js)
        t -= time()
        print(-t, 's')

    def testRegulate(self):
        t = time()
        assert json_loads(js)
        t -= time()
        print(-t, 's')
