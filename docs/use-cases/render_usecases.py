"""Xuất bốn khối PlantUML trong README.md thành SVG.

Chạy từ thư mục gốc: python docs/use-cases/render_usecases.py
Mã nguồn luôn lấy từ Markdown, không sửa tay các file .puml đã trích xuất.
"""
import argparse
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
VERSION="1.2026.9"
DEFAULT_JAR=Path.home()/f".codex/tmp/usecase-plantuml/plantuml-{VERSION}.jar"


def straighten_arrows(root):
    """Giữ bố cục UML, vẽ liên kết trực tiếp từ tác nhân tới biên elip."""
    ns="http://www.w3.org/2000/svg"
    entities={g.get("id"): g for g in root.iter() if g.get("class")=="entity"}
    for link in list(root.iter()):
        if link.get("class")!="link":continue
        pair=[entities[link.get(key)] for key in ("data-entity-1","data-entity-2")]
        actor=next(g for g in pair if "." not in g.get("data-qualified-name", ""))
        case=next(g for g in pair if g is not actor)
        head=actor.find(f"{{{ns}}}ellipse")
        ellipse=case.find(f"{{{ns}}}ellipse")
        cx,cy,rx,ry=(float(ellipse.get(k)) for k in ("cx","cy","rx","ry"))
        ax,ay=float(head.get("cx")),float(head.get("cy"))+16
        labels=actor.findall(f"{{{ns}}}text")
        # Đặt điểm nối ngoài nhãn để các tia chéo không xuyên qua tên tác nhân.
        if ax<cx:
            ax=max([ax+13]+[float(t.get("x"))+float(t.get("textLength","0")) for t in labels])+5
        else:
            ax=min([ax-13]+[float(t.get("x")) for t in labels])-5
        # Nối vào cạnh bên để mũi tên không chạy xuyên các elip ở hàng khác.
        ex,ey=cx-rx if ax<cx else cx+rx,cy
        length=math.hypot(ex-ax,ey-ay)
        ux,uy=(ex-ax)/length,(ey-ay)/length
        points=[(ex,ey),(ex-9*ux-3.5*uy,ey-9*uy+3.5*ux),(ex-9*ux+3.5*uy,ey-9*uy-3.5*ux)]
        for child in list(link):link.remove(child)
        ET.SubElement(link,f"{{{ns}}}path",{"d":f"M {ax:.3f},{ay:.3f} L {ex:.3f},{ey:.3f}","fill":"none","stroke":"#253746","stroke-width":"1.1"})
        ET.SubElement(link,f"{{{ns}}}polygon",{"points":" ".join(f"{x:.3f},{y:.3f}" for x,y in points),"fill":"#253746"})
        link.set("data-rendered-style","straight-arrow")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar",type=Path,default=DEFAULT_JAR)
    args=parser.parse_args()
    if not args.jar.is_file():
        raise SystemExit("Chưa có PlantUML jar; xem hướng dẫn tải trong README của thư mục này.")
    source=(HERE/"README.md").read_text(encoding="utf-8")
    blocks=re.findall(r"```plantuml\s*\n(.*?)```",source,re.S)
    if len(blocks)!=4:raise SystemExit("Cần đúng bốn sơ đồ use case trong Markdown.")
    out=HERE/"diagrams"
    out.mkdir(parents=True,exist_ok=True)
    for block in blocks:
        name=re.search(r"^@startuml\s+([a-z0-9-]+)\s*$",block,re.M)
        if not name or "@enduml" not in block:raise SystemExit("Tên hoặc khối PlantUML không hợp lệ.")
        (out/(name[1]+".puml")).write_text(block.strip()+"\n",encoding="utf-8")
    java=shutil.which("java")
    if java and shutil.which("dot"):
        command=[java,"-Djava.awt.headless=true","-jar",str(args.jar.resolve()),"-charset","UTF-8","-tsvg",str(out/"*.puml")]
    else:
        docker=shutil.which("docker")
        if not docker:
            docker_path=Path.home()/"AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe"
            if docker_path.is_file():docker=str(docker_path)
        if not docker:raise SystemExit("Cần Java hoặc Docker Desktop đang chạy.")
        renderer_image="doan-uml-renderer:1.0"
        exists=subprocess.run([docker,"image","inspect",renderer_image],capture_output=True).returncode==0
        if not exists:
            subprocess.run([docker,"build","-t",renderer_image,str(HERE/"renderer")],check=True,timeout=240)
        font_args=[]
        java_font=[]
        if os.name=="nt":
            # Dùng cùng font Arial ở bước đo chữ Java và khi xem SVG trên Windows.
            font_dir=args.jar.resolve().parent/"fonts"
            font_dir.mkdir(exist_ok=True)
            system_fonts=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"
            for filename in ("arial.ttf","arialbd.ttf","ariali.ttf","arialbi.ttf"):
                if (system_fonts/filename).is_file():shutil.copyfile(system_fonts/filename,font_dir/filename)
            font_args=["-v",f"{font_dir}:/fonts:ro"]
            java_font=["-Dsun.java2d.fontpath=/fonts"]
        # Chỉ dùng Java trong image sẵn có; không khởi động Kafka broker.
        command=[docker,"run","--rm","--network","none","--entrypoint","java",
                 "-v",f"{args.jar.resolve()}:/tools/plantuml.jar:ro",
                 "-v",f"{out.resolve()}:/work",*font_args,
                 renderer_image,"-Djava.awt.headless=true",*java_font,"-jar","/tools/plantuml.jar",
                 "-charset","UTF-8","-tsvg","/work/*.puml"]
    subprocess.run(command,check=True,timeout=120)
    for block in blocks:
        name=re.search(r"^@startuml\s+([a-z0-9-]+)\s*$",block,re.M)[1]
        svg=out/(name+".svg")
        text=svg.read_text(encoding="utf-8")
        if "Syntax Error" in text:raise SystemExit("PlantUML báo lỗi trong "+name)
        # CSS background ở thẻ svg không được mọi trình raster hóa hỗ trợ.
        # Thêm nền trắng thật để chữ/tác nhân vẫn rõ trên Markdown dark mode.
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        root=ET.fromstring(text)
        straighten_arrows(root)
        root.insert(0,ET.Element("{http://www.w3.org/2000/svg}rect",{"width":"100%","height":"100%","fill":"#FFFFFF"}))
        ET.ElementTree(root).write(svg,encoding="utf-8",xml_declaration=False)
        print("OK:",svg.relative_to(HERE))


if __name__=="__main__":main()
