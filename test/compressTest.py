from compress import LikeId as id

l = id(311, 5, "1d5bbd5344fc435e2dd90d00", "http://user.qzone.qq.com/188867099/mood/1be2410be0f6435e9f220900", 
"http://user.qzone.qq.com/1404918557/mood/1d5bbd5344fc435e2dd90d00")

s = l.tostr()
print(s)
print('len =', len(s))
i = id.fromstr(s)
print(i.appid, i.typeid, i.key)
print(i.unikey)
print(i.curkey)