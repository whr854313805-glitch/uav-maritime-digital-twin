"""Materialize machine-local launch paths without changing the F23 presentation.

Uses the existing AnyLogic command-line model runner. No planner/data conversion.
"""
from pathlib import Path
import json
import xml.etree.ElementTree as ET


def startup_code(project, anylogic, python):
    project, anylogic, python = map(lambda p: Path(p).resolve(), (project, anylogic, python))
    jars = sorted((anylogic / 'plugins').glob('com.google.gson_*.jar'))
    if not jars:
        raise FileNotFoundError('AnyLogic Gson library missing: ' + str(anylogic / 'plugins'))
    ui = project / 'anylogic/native-visual-demo.jar'
    for path in (ui, python):
        if not path.is_file():
            raise FileNotFoundError(path)
    literal = lambda p: json.dumps(str(p).replace('\\', '/'), ensure_ascii=False)
    return ('try {\n'
            'java.net.URLClassLoader uiLoader = new java.net.URLClassLoader(new java.net.URL[]{'
            'new java.io.File(' + literal(ui) + ').toURI().toURL(),'
            'new java.io.File(' + literal(jars[-1]) + ').toURI().toURL()},getClass().getClassLoader());\n'
            'uiLoader.loadClass("maritime.NativeDemoView").getMethod("attach",'
            'com.anylogic.engine.Agent.class,String.class,String.class).invoke(null,this,'
            + literal(project) + ',' + literal(python) + ');\n'
            '} catch(Exception e) {throw new RuntimeException("AIS workstation startup failed",e);}\n')


def prepare_model(project, anylogic, python):
    project = Path(project).resolve()
    tree = ET.parse(project / 'anylogic/AIS_Visual_Demo.alp')
    node = tree.find('./Model/ActiveObjectClasses/ActiveObjectClass/StartupCode')
    if node is None:
        raise ValueError('F23 model StartupCode missing')
    node.text = startup_code(project, anylogic, python)
    target = project / '.local/model/AIS_Visual_Demo.alp'
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = ET.tostring(tree.getroot(), encoding='utf-8', xml_declaration=True)
    # Avoid triggering an unnecessary model reload when the launch paths match.
    if not target.exists() or target.read_bytes() != rendered:
        tmp = target.with_suffix('.alp.tmp')
        tmp.write_bytes(rendered)
        tmp.replace(target)
    return target


def template_startup_code():
    """An explicit diagnostic for opening the source template without the launcher."""
    return ('if (System.getProperty("uav.launcher.required", "true").equals("true")) '
            'throw new RuntimeException("Please launch this project using '
            'the root start.cmd or 启动完整演示.cmd. The launcher creates '
            'the machine-local model under .local/model.");\n')
