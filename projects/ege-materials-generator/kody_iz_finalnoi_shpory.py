"""
Коды из файла:
Шаблоны Python на 85 баллов (шпора) - ФИНАЛ 14.pdf

Файл сделан как справочник: все блоки лежат в секциях if False,
чтобы при случайном запуске не выполнялись сразу все задания.
Чтобы использовать код, скопируй нужный блок без строки "if False:".
"""


# ===== №1 =====
if False:
    from itertools import *

    tbl = '348 47 17 128 67 58 235 146'.split()
    graph = 'AF AH HG GC GD DC EC EF FB BD'.split()
    print('1 2 3 4 5 6 7 8')
    for p in permutations('ABCDEFGH'):
        if all(str(p.index(y) + 1) in tbl[p.index(x)] for x, y in graph):
            print(*p)


# ===== №2 =====
if False:
    print("x y w z F")
    p = [0, 1]
    for x in p:
        for y in p:
            for w in p:
                for z in p:
                    F = w and (not y) and ((not x) or z)
                    if F == 1:
                        print(x, y, w, z, F)


# ===== №5 =====
if False:
    def tri(x):
        a = ''
        while x > 0:
            a = str(x % 3) + str(a)
            x = x // 3
        return a

    for n in range(1, 1000):
        n3 = tri(n)
        if n % 3 == 0:
            n3 = '1' + n3 + '02'
        else:
            n3 = n3 + tri((n % 3) * 5)
        r = int(n3, 3)
        if r >= 177:
            print(n)
            break


# ===== №6 =====
if False:
    from turtle import *

    tracer(0)
    screensize(2500, 2500)
    lt(90)
    pendown()
    k = 25
    for i in range(3):
        fd(32 * k)
        rt(90)
        fd(38 * k)
        rt(90)
    penup()
    fd(25 * k)
    rt(90)
    fd(21 * k)
    lt(90)
    pendown()
    for i in range(3):
        fd(29 * k)
        rt(90)
        fd(-18 * k)
        rt(90)
    penup()
    for x in range(-60, 60):
        for y in range(-60, 60):
            goto(x * k, y * k)
            dot(5, 'red')
    update()


# ===== №8 =====
if False:
    from itertools import *

    c = 0
    for i in product(sorted('строка'), repeat=5):
        a = ''.join(i)
        c += 1
        b = a.replace('а', '-').replace('с', '-').replace('т', '-')
        if b[0] != '-' and a.count('о') == 2 and c % 2 == 0:
            print(c)


# ===== №9 Excel =====
"""
№9 сделан в PDF как Excel-шпаргалка.

Основные формулы:

Считаем, сколько раз значение A1 входит в строку A1:G1:
=СЧЁТЕСЛИ($A1:$G1;A1)

Одно число повторяется дважды, остальные 5 различны:
=ЕСЛИ(СУММ(H1:N1)=9;1;0)

Выписать повторяющиеся числа:
=ЕСЛИ(H1>1;A1;"")

Выписать неповторяющиеся числа:
=ЕСЛИ(H1=1;A1;"")

Среднее повторяющихся:
=ЕСЛИ(O1=1;СРЗНАЧ(P1:V1);0)

Среднее неповторяющихся:
=ЕСЛИ(O1=1;СРЗНАЧ(W1:AC1);1)

Проверить оба условия:
=ЕСЛИ(O1+AF1=2;1;0)

Четное число:
=ЕСЛИ(ОСТАТ(A1;2)=0;1;0)

Оканчивается на 5:
=ЕСЛИ(ОСТАТ(A1;10)=5;1;0)

Проверка точного количества через НАИБОЛЬШИЙ:
=ЕСЛИ(И(НАИБОЛЬШИЙ(A1:F1;3)=3;НАИБОЛЬШИЙ(A1:F1;4)=1);1;0)
"""


# ===== №11 =====
if False:
    from math import *

    # Мощность алфавита
    for n in range(1, 1000):
        i = ceil(log2(n))
        ser = ceil(377 * i / 8)
        if 23155 * ser > 5536 * 1024:
            print(n)
            break

    # Длина кода
    alphabet = 10 + 26 + 496
    i = ceil(log2(alphabet))
    for length in range(1, 1000):
        one_number = ceil(length * i / 8)
        if 725 * one_number > 353 * 1024:
            print(length)
            break


# ===== №13 =====
if False:
    from ipaddress import *

    # Сколько IP-адресов в сети
    net = ip_network('211.46.0.0/255.255.128.0')
    cnt = 0
    for ip in net:
        s = f'{int(ip):032b}'
        if s.count('1') % 4 == 0 and s[-2:] == '11':
            cnt += 1
    print(cnt)

    # Наибольший IP-адрес, сумма чисел в адресе
    net = ip_network('143.168.72.213/255.255.254.240', 0)
    print(max(sum(map(int, str(ip).split('.'))) for ip in net))


# ===== №14 =====
if False:
    # Вариант 1
    def elev(x):
        a = []
        while x > 0:
            a.insert(0, x % 11)
            x = x // 11
        return a

    for x in range(3001):
        k = 9 * 11**210 + 8 * 11**150 - x
        if elev(k).count(0) == 60:
            print(x)

    # Вариант 2
    c = 0

    def tws(x):
        a = []
        while x > 0:
            a.insert(0, x % 27)
            x = x // 27
        return a

    a = 2 * 2187**567 + 729**566 - 2 * 243**565 + 81**564 - 2 * 27**563 - 6561
    for i in tws(a):
        if i > 9 and i % 2 == 0:
            c += 1
    print(c)


# ===== №15 =====
if False:
    # Неравенства
    def f(x, y):
        return (x > A) or (y > A) or (y < (x - 2)) or (y > (2 * x - 10))

    for A in range(0, 1000):
        if all(f(x, y) == 1 for x in range(1, 1000) for y in range(1, 1000)):
            print(A)

    # Отрезки, max длина
    P = list(range(3, 44))
    Q = list(range(21, 63))
    A = list(range(100))

    def f(x):
        return ((x in Q) <= (x in P)) <= (not (x in A))

    for x in range(100):
        if f(x) == 0:
            A.remove(x)
    print(A)

    # Отрезки, min длина
    B = list(range(15, 41))
    C = list(range(21, 64))
    A = list()

    def f(x):
        return (not (x in B)) <= (((x in C) and (not (x in A))) <= (x in B))

    for x in range(1, 100):
        if f(x) == 0:
            A.append(x)
    print(A)

    # Поразрядная конъюнкция
    def f(x):
        return ((x & 42 != 0) and (x & 34 == 0)) <= (not (x & A == 0))

    for A in range(0, 1000):
        if all(f(x) == 1 for x in range(0, 1000)):
            print(A)

    # Делимость
    def f(x):
        return ((x % 26 != 0) and (x % A == 0)) <= ((x % 39 == 0) or (x % A != 0))

    for A in range(1, 1000):
        if all(f(x) == 1 for x in range(0, 1000)):
            print(A)

    # DELL
    def DELL(x):
        return (x % 128 == 0) <= ((x % A != 0) <= (x % 80 != 0))

    for A in range(1, 1000):
        if all(DELL(x) == 1 for x in range(1, 1000)):
            print(A)


# ===== №16 =====
if False:
    import sys

    sys.setrecursionlimit(100000)

    def g(n):
        if n <= 20:
            return n + 2
        if n > 20:
            return g(n - 3) + 1

    def f(n):
        return 3 * g(n - 3) + 7

    print(f(37811))


# ===== №17 =====
if False:
    # Двойки
    def ch(x):
        if len(str(abs(x))) == 3:
            return 1
        else:
            return 0

    s = [int(x) for x in open('17_232033.txt')]
    sp = []
    m = 1000000000000
    for i in range(len(s)):
        if abs(s[i]) % 10 == 7 and ch(s[i]) == 1:
            m = min(m, s[i])
    for i in range(len(s) - 1):
        if (ch(s[i]) + ch(s[i + 1])) == 1 and ((s[i] + s[i + 1]) % m == 0):
            sp.append(s[i] + s[i + 1])
    print(len(sp), min(sp))

    # Тройки
    def hz(x):
        if len(str((abs(x)))) == 2:
            return 1
        else:
            return 0

    s = [int(s) for s in open('/Users/timka/Documents/17_29971.txt')]
    tp = []
    max33 = max(x for x in s if abs(x) % 100 == 33)
    for i in range(len(s) - 2):
        if hz(s[i]) + hz(s[i + 1]) + hz(s[i + 2]) == 2 and ((s[i] + s[i + 1] + s[i + 2]) ** 2) < max33:
            tp.append(s[i] + s[i + 1] + s[i + 2])
    print(len(tp), max(tp))


# ===== №19-21: одна куча =====
if False:
    def f(k, h):
        if k <= 15:
            return h % 2 == 0
        if h == 0:
            return 0
        l = [f(k - 3, h - 1), f(k - 7, h - 1), f(k // 4, h - 1)]
        if (h - 1) % 2 == 0:
            return any(l)
        else:
            return all(l)

    # №19
    for s in range(16, 100):
        if f(s, 1) == 0 and f(s, 2) == 1:
            print(s)

    # №20
    for s in range(16, 100):
        if f(s, 1) == 0 and f(s, 3) == 1:
            print(s)

    # №21
    for s in range(16, 100):
        if f(s, 2) == 0 and f(s, 4) == 1:
            print(s)


# ===== №19-21: две кучки =====
if False:
    # №19: неудачный ход -> any
    def f(m, n, k):
        if m + n >= 65:
            return k % 2 == 0
        if k == 0:
            return 0
        h = [f(m + 1, n, k - 1), f(m * 3, n, k - 1), f(m, n + 1, k - 1), f(m, n * 3, k - 1)]
        if (k - 1) % 2 == 0:
            return any(h)
        else:
            return any(h)

    for s in range(1, 59):
        if f(6, s, 2) == True and f(6, s, 1) == 0:
            print(s)

    # №20-21: обычная проверка -> all
    def f(m, n, k):
        if m + n >= 65:
            return k % 2 == 0
        if k == 0:
            return 0
        h = [f(m + 1, n, k - 1), f(m * 3, n, k - 1), f(m, n + 1, k - 1), f(m, n * 3, k - 1)]
        if (k - 1) % 2 == 0:
            return any(h)
        else:
            return all(h)

    for s in range(1, 59):
        if f(6, s, 3) == 1 and f(6, s, 1) == 0:
            print(s)

    for s in range(1, 59):
        if f(6, s, 4) == 1 and f(6, s, 2) == 0:
            print(s)


# ===== №23 =====
if False:
    def f(n, m):
        if n > m or n == 7:
            return 0
        if n == m:
            return 1
        return f(n + 1, m) + f(n + 3, m) + f(n * 2, m)

    print(f(2, 15) * f(15, 25))


# ===== №24 =====
if False:
    # Два указателя
    s = open('24_24387.txt').readline()
    s = s.replace('0', '+').replace('2', '+').replace('4', '+').replace('6', '+').replace('8', '+')
    crs = 0
    mmax = 0
    l = 0
    lans = 0
    for r in range(1, len(s)):
        if (s[r] in '13579' and s[r - 1] in '13579') or (s[r] == '+' and s[r - 1] == '+'):
            if mmax < crs:
                mmax = crs
                lans = l
            crs = 0
            l = r
        elif s[r] in '13579':
            crs += int(s[r])
    if mmax < crs:
        mmax = crs
        lans = l
    print(lans)

    # Регулярки для арифметического выражения
    from re import *

    s = open('24.txt').readline()
    num = '([789][0789]*|0)'
    match = f'{num}([-*]{num})+'
    ans = [x.group() for x in finditer(match, s)]
    print(max(len(x) for x in ans))


# ===== №25 =====
if False:
    from fnmatch import *

    # Маски
    for i in range(1917, 10**10, 1917):
        if fnmatch(str(i), '3?12214*5'):
            print(i, i // 1917)

    # Делители
    def dels(n):
        mn = set()
        for i in range(2, int(n**0.5) + 1):
            if n % i == 0:
                mn.add(i)
                mn.add(n // i)
        return mn

    def prost(n):
        return n > 1 and all(n % i != 0 for i in range(2, int(n**0.5) + 1))

    k = 0
    for x in range(1324727 + 1, 200000000000):
        d = dels(x)
        dpr = [y for y in d if prost(y)]
        maxd = 0

        if len(dpr) == 1 and dpr[0] ** 2 == x and str(dpr[0]).count('5') == 1:
            maxd = dpr[0]

        if len(dpr) == 2 and dpr[0] * dpr[1] == x and str(dpr[0]).count('5') == 1 and str(dpr[1]).count('5') == 1:
            maxd = max(dpr)

        if maxd > 0:
            print(x, maxd)
            k += 1
            if k == 5:
                break


# ===== №27 =====
if False:
    from math import dist

    cla = [[], []]
    for s in open('27A.txt'):
        s = s.replace(',', '.')
        x, y, har = s.split()
        x, y = float(x), float(y)
        col, svet, r = har[0], har[1], har[2:]
        if y > 10:
            cla[0].append([x, y, col, svet, r])
        else:
            cla[1].append([x, y, col, svet, r])

    clb = [[], [], []]
    for s in open('27B.txt'):
        s = s.replace(',', '.')
        x, y, har = s.split()
        x, y = float(x), float(y)
        col, svet, r = har[0], har[1], har[2:]
        if x > 22:
            clb[0].append([x, y, col, svet, r])
        elif y > 22:
            clb[1].append([x, y, col, svet, r])
        else:
            clb[2].append([x, y, col, svet, r])

    def center(cl):
        minsum = 10**9
        best = None
        for p in cl:
            summa = sum(dist(p[:2], p1[:2]) for p1 in cl)
            if summa < minsum:
                minsum = summa
                best = p
        return best

    cla.sort(key=len)
    cent = center(cla[0])
    sky = cla[0] + cla[1]
    a1 = min(dist(cent[:2], [x, y]) for x, y, col, svet, r in sky if col + r == 'YIII') * 10000
    a2 = max(dist(cent[:2], [x, y]) for x, y, col, svet, r in sky if col + r == 'YIII') * 10000
    print(int(a1), int(a2))

    b1 = 10**9
    for cl in clb:
        for x1, y1, col1, svet1, r1 in cl:
            for x2, y2, col2, svet2, r2 in cl:
                if not (x1 == x2 and y1 == y2) and col1 + r1 == col2 + r2 == 'ZI':
                    b1 = min(b1, dist([x1, y1], [x2, y2]))

    b2 = dist(center(clb[0])[:2], center(clb[2])[:2])
    print(int(b1 * 10000), int(b2 * 10000))
