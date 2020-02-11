from compress import LikeId as id

l = id(311, 5, "0fae732e6aa03f5e32480d00", "http://user.qzone.qq.com/1113426273/mood/61895d42256e3f5ef3af0d00", 
"http://user.qzone.qq.com/779333135/mood/0fae732e6aa03f5e32480d00")

s = l.tostr()
print(s)
print('len =', len(s))
i = id.fromstr(s)
print(i.appid, i.typeid, i.key)
print(i.unikey)
print(i.curkey)