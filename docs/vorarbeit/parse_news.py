import sys, json, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
d = sys.argv[1]
# Google News
r = ET.parse(d+'/gn.xml').getroot()
items = r.findall('./channel/item')
print('GN items', len(items))
for it in items[:3]:
    print({c.tag: (c.text or '')[:100] for c in it}, {c.tag: c.attrib for c in it if c.attrib})
dates = sorted(parsedate_to_datetime(it.findtext('pubDate')) for it in items)
print('GN oldest', dates[0], 'newest', dates[-1])
print('GN desc raw:', items[0].findtext('description')[:400])
# tagesschau JSON
j = json.load(open(d+'/ts.json'))
print('TS keys', list(j.keys()))
n = j['news']
print('TS count', len(n))
print('TS item keys', sorted(n[0].keys()))
for x in n[:5]:
    print(x.get('date'), x.get('ressort'), x.get('regionId'), x.get('regionIds'), x.get('type'), '|', x.get('title'), '|', (x.get('firstSentence') or '')[:100], '|', x.get('shareURL') or x.get('detailsweb'), x.get('tags', [])[:4], x.get('topline'), x.get('breakingNews'))
print('TS ressorts', sorted(set(str(x.get('ressort')) for x in n)))
print('TS types', sorted(set(str(x.get('type')) for x in n)))
print('TS nextPage', j.get('nextPage'), j.get('newStoriesCountLink'), j.get('type'))
# tagesschau RSS
r = ET.parse(d+'/ts_rss.xml').getroot()
items = r.findall('./channel/item')
print('TS RSS items', len(items))
for it in items[:2]:
    print({c.tag: (c.text or '')[:100] for c in it})
# DW RDF
ns = {'rss':'http://purl.org/rss/1.0/','dc':'http://purl.org/dc/elements/1.1/','rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#'}
r = ET.parse(d+'/dw.xml').getroot()
items = r.findall('rss:item', ns)
print('DW items', len(items))
for it in items[:3]:
    print(it.findtext('rss:title',namespaces=ns), '|', it.findtext('dc:date',namespaces=ns), '|', it.findtext('dc:subject',namespaces=ns), '|', (it.findtext('rss:description',namespaces=ns) or '')[:100], '|', it.findtext('rss:link',namespaces=ns))
print('DW child tags', [c.tag for c in items[0]])
