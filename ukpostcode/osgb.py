"""OSGB36 easting/northing -> WGS84 lat/lng (Helmert, ~5 m accuracy)."""
from math import sin, cos, tan, sqrt, atan2, radians, degrees, pi
def _en_to_osgb(E, N):
    a, b = 6377563.396, 6356256.909; F0 = 0.9996012717
    lat0, lon0 = radians(49), radians(-2); N0, E0 = -100000, 400000
    e2 = 1 - (b * b) / (a * a); n = (a - b) / (a + b)
    lat, M = lat0, 0
    while True:
        lat = (N - N0 - M) / (a * F0) + lat
        Ma = (1 + n + 5/4*n**2 + 5/4*n**3) * (lat - lat0)
        Mb = (3*n + 3*n**2 + 21/8*n**3) * sin(lat - lat0) * cos(lat + lat0)
        Mc = (15/8*n**2 + 15/8*n**3) * sin(2*(lat - lat0)) * cos(2*(lat + lat0))
        Md = 35/24*n**3 * sin(3*(lat - lat0)) * cos(3*(lat + lat0))
        M = b * F0 * (Ma - Mb + Mc - Md)
        if abs(N - N0 - M) < 0.00001: break
    nu = a*F0/sqrt(1 - e2*sin(lat)**2); rho = a*F0*(1 - e2)/(1 - e2*sin(lat)**2)**1.5; eta2 = nu/rho - 1
    t = tan(lat); s = 1/cos(lat)
    VII = t/(2*rho*nu); VIII = t/(24*rho*nu**3)*(5 + 3*t**2 + eta2 - 9*t**2*eta2); IX = t/(720*rho*nu**5)*(61 + 90*t**2 + 45*t**4)
    X = s/nu; XI = s/(6*nu**3)*(nu/rho + 2*t**2); XII = s/(120*nu**5)*(5 + 28*t**2 + 24*t**4); XIIA = s/(5040*nu**7)*(61 + 662*t**2 + 1320*t**4 + 720*t**6)
    dE = E - E0
    return lat - VII*dE**2 + VIII*dE**4 - IX*dE**6, lon0 + X*dE - XI*dE**3 + XII*dE**5 - XIIA*dE**7
def to_wgs84(E, N):
    lat, lon = _en_to_osgb(E, N)
    a, b = 6377563.396, 6356256.909; e2 = 1 - b*b/(a*a); nu = a/sqrt(1 - e2*sin(lat)**2)
    x = nu*cos(lat)*cos(lon); y = nu*cos(lat)*sin(lon); z = (1 - e2)*nu*sin(lat)
    tx, ty, tz, s = 446.448, -125.157, 542.060, -20.4894e-6
    rx, ry, rz = [radians(v/3600) for v in (0.1502, 0.2470, 0.8421)]
    x2 = tx + (1 + s)*x - rz*y + ry*z; y2 = ty + rz*x + (1 + s)*y - rx*z; z2 = tz - ry*x + rx*y + (1 + s)*z
    a, b = 6378137.0, 6356752.3141; e2 = 1 - b*b/(a*a); p = sqrt(x2*x2 + y2*y2)
    lat = atan2(z2, p*(1 - e2))
    for _ in range(10): lat = atan2(z2 + e2*a/sqrt(1 - e2*sin(lat)**2)*sin(lat), p)
    return round(degrees(lat), 6), round(degrees(atan2(y2, x2)), 6)
