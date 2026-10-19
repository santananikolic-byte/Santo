#!/usr/bin/env python3
import os, glob
here=os.path.dirname(os.path.abspath(__file__))
order=['00_core.js','05_assets.js','06_env.js','10_audio.js','64_roster.js','65_storydata.js','20_rig.js','22_skin.js','23_mocap.js','30_fx.js','40_city.js','50_world.js','60_kombat.js','62_props.js','70_story.js','80_ui.js','90_main.js']
import base64
glb=os.path.join(here,'assets','hero.glb')
glb=os.path.join(here,"assets","chars","hero.glb")
skin="const SKIN_GLB = \""+(base64.b64encode(open(glb,"rb").read()).decode() if os.path.exists(glb) else "")+"\";\n"
js=skin+'\n'.join(open(os.path.join(here,'src',f),encoding='utf-8').read() for f in order)
shell=open(os.path.join(here,'shell.html'),encoding='utf-8').read()
page=shell.replace('/*__GAME__*/', js)
open(os.path.join(here,'silkstrike.html'),'w',encoding='utf-8').write(page)
full='<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">\n'+page.replace('<canvas id="game">','</head>\n<body>\n<canvas id="game">',1)+'\n</body>\n</html>\n'
open(os.path.join(here,'index.html'),'w',encoding='utf-8').write(full)
print('ok', len(page)//1024, 'KB')

import subprocess, sys
subprocess.run([sys.executable, os.path.join(here, 'pack.py')], check=True)
