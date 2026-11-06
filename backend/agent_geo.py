"""Offline approximate IP location. No visitor address leaves this machine."""
import functools,ipaddress,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
from ip2region import util,searcher

@functools.lru_cache(maxsize=2)
def database(version):
    path=ROOT/'geo-data'/f'ip2region_v{version}.xdb'
    util.verify_from_file(str(path))
    return searcher.new_with_buffer(util.IPv4 if version==4 else util.IPv6,path.read_bytes())

@functools.lru_cache(maxsize=8192)
def locate(value):
    result={'label':'位置未知','approximate':True,'source':'ip2region'}
    try:ip=ipaddress.ip_address(value)
    except ValueError:return result
    if ip.version==6 and ip.ipv4_mapped:ip=ip.ipv4_mapped
    if ip in ipaddress.ip_network('100.64.0.0/10') or ip in ipaddress.ip_network('fd7a:115c:a1e0::/48'):return {**result,'label':'尾网地址 · 无公网归属地'}
    if ip.is_loopback:return {**result,'label':'本机地址'}
    if ip.is_private:return {**result,'label':'局域网或保留地址'}
    if not ip.is_global:return {**result,'label':'非公网地址'}
    try:
        fields=database(ip.version).search(str(ip)).split('|')
        if len(fields)>=4:
            names=('country','region','city','isp')
            result.update({k:v for k,v in zip(names,fields[:4]) if v and v!='0'})
            parts=list(dict.fromkeys(result[k] for k in names if result.get(k)))
            if parts:result['label']=' · '.join(parts)
    except (OSError,ValueError):pass
    return result
