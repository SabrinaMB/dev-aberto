#!/usr/bin/env python3

import jinja2 as j2
import markdown
import os
import json
import pprint
import io
import re
import copy
import markdown
import tabulate
import itertools

import sys
import time

from utils import load_key, create_key, write_string_to_file, load_encrypted, save_encrypted
from students import Student, all_students, project_points
from skills import Skill, all_skills


import click

from collections import namedtuple

PR = namedtuple('PR', ['project_name', 'url', 'status'])

@click.group()
def dev_aberto_cli():
    pass

@dev_aberto_cli.command()
def new_user():
    student_login = ''

    while student_login == '':
        student_login = input('login insper: ').strip()

    student_key = create_key(f'students/{student_login}.key')
    student_name = input('nome completo: ')
    ghname = input('usuário do github: ')
    s = Student(student_login, student_name, ghname, [])
    write_string_to_file(f'students/{student_login}', s.toJSON())
    
    save_encrypted(f'students/{student_login}-achievements', student_key, '[]')


@dev_aberto_cli.command()
@click.argument('student_login')
def edit_achievements(student_login):
    key = load_key(f'students/{student_login}.key')
    json_achievements = load_encrypted(f'students/{student_login}-achievements', key)

    with open(f'students/{student_login}.temp', 'w') as f:
        f.write(json_achievements)
    
    if 'win32' in sys.platform:
        editor = os.getenv('EDITOR', default='notepad.exe')
    else:
        editor = os.getenv('EDITOR', default='vi')
    
    while True:
        os.system(f'{editor} students/{student_login}.temp')
        with open(f'students/{student_login}.temp') as f:
            json_achievements = f.read()
        try:
            _ = json.loads(json_achievements)
        except json.JSONDecodeError:
            print("Arquivo mal formatado.")
            time.sleep(2)
            continue
    
        print('Validando skills no arquivo JSON....')
        s = Student.load(student_login)
        s._load_skills_from_string(json_achievements)
        valid_skills = True
        for ach in s.all_achievements:
            try:
                ach.validate_metadata()
            except ValueError as e:
                print('- ', ach, '\n\t', e)
                valid_skills = False
        if valid_skills:
            break
        time.sleep(2)
        print('\n\n==================')
    print('Nenhum erro encontrado!')
    save_encrypted(f'students/{student_login}-achievements', key, json_achievements)

    os.remove(f'students/{student_login}.temp')

def load_skill_and_check_done(skill_name, st):
    skill_list = [copy.deepcopy(sk) for sk in all_skills.values() if sk.type == skill_name]
    for sk in skill_list:
        sk.done = False
        if sk.id in [3, 11, 12]:
            sk.done = True # nao eh obrigatoria
        for ach in st.achievements:
            if sk.id == ach.skill.id:
                sk.done = True
    return skill_list

def student_has_skill(st, skill):
    xp_total = -1
    for ach in st.achievements.get(skill.id, []):
        xp_total += ach.xp()
    return xp_total

@dev_aberto_cli.command()
@click.argument('student_login')
def compute_grade(student_login):
    print(f'{student_login}:')
    st = all_students[student_login]

    env = j2.Environment(loader=j2.FileSystemLoader('templates/'))

    feedback_template = env.get_template('report.html')
    
    mandatoryD = [sk for sk in all_skills.values() if sk.mandatory == 'D']
    doneD = [(student_has_skill(st, sk), sk) for sk in mandatoryD]

    mandatoryC = [sk for sk in all_skills.values() if sk.mandatory == 'C']
    doneC = [(student_has_skill(st, sk), sk) for sk in mandatoryC]

    mandatoryB = [sk for sk in all_skills.values() if sk.mandatory == 'B']
    doneB = [(student_has_skill(st, sk), sk) for sk in mandatoryB]

    done_all = [ach for ach in st.all_achievements if ach.skill.mandatory == '-']
    done_all = sorted(done_all, key=lambda t: t.date)

    conceito = 'I'

    xp = st.compute_grade()

    html = feedback_template.render(doneD=doneD,
                                    doneC=doneC,
                                    doneB=doneB,
                                    doneAll=done_all,
                                    xp_total=xp, st=st, conceito=conceito,
                                    )
    with open(f'students/{student_login}-report.html', 'w') as f:
        f.write(html)

    print('------------')
    print('Conceito final:', conceito)
    print(xp)
    print('Nota de grupo:', project_points[student_login])

@dev_aberto_cli.command()
@click.pass_context
def report_cards(ctx):
    print(ctx, all_students.keys())
    for st_login in all_students.keys():
        print('st_login', st_login)        
        ctx.invoke(compute_grade, student_login=st_login)

    # TODO: envia e-mail

@dev_aberto_cli.command()
def list_users():
    for st in all_students.values():
        k = '*' if st.has_key else ''
        print(f'{st.name}{k}')

def render_skill_type(sk_type):
    table = [(sk.id, sk.material_icon, sk.name, sk.descr, sk.xp)
                for sk in all_skills.values() if sk.type == sk_type.title()]
    with open(f'docs/_snippets/skills-{sk_type}.md', 'w') as f:
        f.write(tabulate.tabulate(table, headers=('id', '', 'Nome', 'Descrição', 'XP'), tablefmt='pipe'))

def parse_url(url):
    m = re.match('https?://github.com/(.*)/([\w\-]+)/(pull|issues)/(\d+)', url)
    if m:
        if m.group(3) == "pull":
            pulls_issues = "pulls"
        else:
            pulls_issues = "issues"
        status = "https://img.shields.io/github/"+ pulls_issues +"/detail/state/" + m.group(1)+"/"+m.group(2)+"/"+ m.group(4)+ "?label=%20"
        return PR(m.group(2), url, status)
    return PR('Outros', url, '')

def dict_add_to_list(d, el, url):
    if not el in d:
        d[el] = []
    d[el].append(url)

def dict_add_to_dict(d, el, sub, url):
    if not el in d:
        d[el] = {}
    if not sub in d[el]:
        d[el][sub] = []
    d[el][sub].append(url)

@dev_aberto_cli.command()
def build_site():
    env = j2.Environment(loader=j2.FileSystemLoader('templates/'))

    render_skill_type('tutorial')
    render_skill_type('code')
    render_skill_type('community')
    render_skill_type('docs')
    
    students = []
    for st_login in sorted(all_students.keys()):
        st = all_students[st_login]
        students.append([
            f'![{st.name}]({st.avatar}){{: style="max-width:64px; valign="center"}}',
            st.name.title(), 
            f'[![](css/github.png)](http://github.com/{st.ghuser})'
        ])
    with open('docs/_snippets/alunos.md', 'w') as f:
        f.write(tabulate.tabulate(students, headers=('', '', ''), tablefmt='pipe'))
        
    impacto_template = env.get_template('impacto.html')
    info = {}
    info_insper = []
    eventos = set()
    num_eventos = 0
    num_aceitos = 0
    for student in all_students.values():
        for ach in student.all_achievements:
            if ach.skill.id == 10 and ach.user == student:
                info_insper.append(ach)

            if ach.skill.id == 40 and ach.user == student:
                num_eventos += 1
                if 'picture' in ach.metadata:
                    eventos.add((ach.metadata['picture'], ach.metadata.get('url', '#')))

            if ach.skill.id == 22 and ach.user == student:
                num_aceitos += 1

            # Skill Minha primeira contribuição
            if ach.skill.id == 3 and ach.user == student:
                if isinstance(ach.metadata, dict):
                    url = ach.metadata['url']
                else:
                    url = ach.metadata
                data = parse_url(url)
                dict_add_to_dict(info, data.project_name, 'Pull Requests', data)

            
            if ach.skill.id in [20, 21] and ach.user == student:
                if isinstance(ach.metadata, dict):
                    url = ach.metadata['url']
                else:
                    url = ach.metadata
                data = parse_url(url)
                dict_add_to_dict(info, data.project_name, 'Issues', data)

    with open('docs/impacto.md', 'w') as f:
        num_projetos = len(info)
        num_prs = 0
        for proj in info:
            prs_proj = info[proj].get('Pull Requests', [])
            num_prs += len(prs_proj)
        sorted_keys = sorted(info.keys(), key=lambda t: -len(info[t].get('Pull Requests', [])))
        f.write(impacto_template.render(data=info,
                                        info_insper=info_insper,
                                        eventos=eventos,
                                        num_eventos=num_eventos,
                                        sorted_keys=sorted_keys, 
                                        num_projetos=num_projetos, 
                                        num_prs=num_prs, 
                                        num_aceitos=num_aceitos))

if __name__ == '__main__':

    dev_aberto_cli()
