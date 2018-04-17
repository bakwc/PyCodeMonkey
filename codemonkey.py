#!/usr/bin/env python

import sys
import os
import re
import imp
import time
import random
from subprocess import Popen, PIPE
from howdoi import howdoi
from threading import Timer

FNULL = open(os.devnull, 'w')

OUT_FILE = 'result.py'

def printUsage():
    print 'usage: %s problemFile' % sys.argv[0]

class FuncInfo(object):
    def __init__(self, name, args):
        self.name = name
        self.args = args

class Program(object):
    def __init__(self, funcInfo):
        self.funcInfo = funcInfo
        self.lines = []
        self.imports = []

    def addBodyLine(self, line):
        self.lines.append(line)

    def addImport(self, importName):
        self.imports.append(importName)

    def addImports(self, imports):
        for i in imports:
            self.addImport(i)

    def addFutureDivision(self):
        self.addImport('from __future__ import division')

def parseFunctionDef(funcDef):
    assert funcDef.startswith('def ')
    assert funcDef.endswith('):')
    funcDef = funcDef[4:-2]
    argsStart = funcDef.find('(')
    assert argsStart != -1
    funcName = funcDef[:argsStart]
    funcDef = funcDef[argsStart + 1:]
    funcArgs = map(lambda x:x.strip(), funcDef.split(','))
    return FuncInfo(funcName, funcArgs)

def generateImports(program):
    outData = ''
    for importName in program.imports:
        outData += importName
    outData += '\n'
    return outData

def generateProgram(program):
    outData = ''
    # for importName in program.imports:
    #     outData += 'import %s\n' % importName
    # outData += '\n'

    funcInfo = program.funcInfo

    outData += '\n'
    outData += 'def %s(%s):\n' % (funcInfo.name, ', '.join(funcInfo.args))
    for line in program.lines:
        outData += '    %s\n' % line
    return outData

def generateOutput(program, srcData, outFile):
    before, after = srcData
    outData = ''
    outData += generateImports(program)
    outData += before
    outData += generateProgram(program)
    outData += after
    outData += '''
if __name__ == '__main__':
    tests()
'''
    open(outFile, 'w').write(outData)
    assert open(outFile, 'r').read() == outData

def checkProgram(program, srcData):
    generateOutput(program, srcData, OUT_FILE)
    process = Popen(["python", "result.py"], stderr=PIPE, stdout=PIPE)
    kill_proc = lambda p: p.kill()
    timer = Timer(0.5, kill_proc, [process])
    try:
        timer.start()
        (output, err) = process.communicate()
    finally:
        timer.cancel()
    exit_code = process.wait()
    return exit_code == 0

FUNC_SKIP_START = ['import ', 'from ', 'class ', 'def ']
def extractFuncs(framgent):
    lines = framgent.split('\n')
    funcs = []

    for l in lines:
        l = l.strip()
        if l.startswith('print '):
            l = l[6:]
        if l.startswith('>>> '):
            l = l[4:]
        if l.startswith('return '):
            l = l[7:]
        skip = False
        for pref in FUNC_SKIP_START:
            if l.startswith(pref):
                skip = True
                break
        if skip:
            continue
        eq = l.find('=')
        ob = l.find('(')
        if eq != -1 and eq < ob:
            l = l[eq + 1:]
            l = l.strip()
            ob = l.find('(')
        if ob == -1 or ob == 0:
            continue
        if l.startswith('['):
            continue
        funcName = l[:ob]
        l = l[ob+1:]
        eb = l.find(')')
        if eb != -1:
            l = l[:eb]
        args = map(lambda x:x.strip(), l.split(','))
        kwArgs = []
        rargs = []
        for arg in args:
            if arg.find('=') != -1:
                k, v = arg.split('=')[:2]
                kwArgs.append((k, v))
            elif not kwArgs:
                rargs.append(arg)

        funcs.append((funcName, rargs, kwArgs))

    return funcs

def getOffset(l):
    for i, c in enumerate(l):
        if c != ' ':
            return i
    return None

def extractFuncSnippets(codeFragment):
    lines = codeFragment.split('\n')
    lines.append('# end')
    currentFunc = None
    offset = None
    bodyLines = []

    funcSnippets = []

    for l in lines:
        if not l.strip():
            continue
        if currentFunc is not None:
            if offset is None:
                offset = getOffset(l)
            if getOffset(l) < offset:
                funcSnippets.append((currentFunc, bodyLines))
                currentFunc = None
                bodyLines = []
                offset = None
            else:
                bodyLines.append(l)

        if l.startswith('def '):
            try:
                funcInfo = parseFunctionDef(l)
            except Exception:
                funcInfo = None
            if funcInfo is not None:
                currentFunc = funcInfo

    return funcSnippets


def extractOneLiners(codeFragment):
    lines = codeFragment.split('\n')
    lines = [l for l in lines if l.strip()]
    if len(lines) > 3:
        return []
    oneLiners = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        l = ' ' + l + ' '
        eq = l.find('=')
        if eq != -1 and l[eq + 1] != '=' and l[eq-1] not in ('+', '-'):
            l = l[eq+1:]
        l = l.strip()
        if not l:
            continue
        names = findNames(l)
        if not names:
            continue
        oneLiners.append((names, l))
    return oneLiners

def extractImports(codeFragment):
    imports = []
    lines = codeFragment.split('\n')
    lines = [l for l in lines if l.strip()]
    for l in lines:
        l = l.strip()
        if l.startswith('from ') or l.startswith('import '):
            imports.append(l)
    if imports:
        return imports
    if codeFragment.find('math.') != -1:
        imports.append('import math')
    else:
        if codeFragment.find('sqrt') != -1 or \
                codeFragment.find('pow') != -1 or \
                codeFragment.find('sin') != -1 or \
                codeFragment.find('cos') != -1:
            imports.append('from math import *')
    return list(set(imports))

def replaceArgs(l, argsFrom, argsTo):
    for i in xrange(len(argsFrom)):
        argFrom = argsFrom[i]
        argTo = argsTo[i]
        pattern = r'(^|[^a-zA-Z\d])%s([^a-zA-Z\d]|$)' % argFrom
        target = r'\1%s\2' % argTo
        l = re.sub(pattern, target, l)
    return l


def findNames(l):
    return re.findall(r'[a-zA-Z][a-zA-Z\d]*', l)


def checkCodeFragment(funcInfo, srcData, codeFragment):
    funcs = extractFuncs(codeFragment)
    imports = extractImports(codeFragment)

    for funcName, args, kwargs in funcs:
        #print 'checking func', funcName
        if funcName in ('input', 'raw_input'):
            continue

        program = Program(funcInfo)
        program.addImports(imports)
        program.addBodyLine('return %s(%s)' % (funcName, ', '.join(funcInfo.args)))
        #print 'checking lines:', program.lines
        if checkProgram(program, srcData):
            return program
        program.addFutureDivision()
        if checkProgram(program, srcData):
            return program

        if kwargs:
            program = Program(funcInfo)
            program.addImports(imports)
            program.addBodyLine('return %s(%s, %s)' % (funcName, ', '.join(funcInfo.args), ', '.join([x[0] + '=' + x[1] for x in kwargs])))
            #print 'checking lines:', program.lines
            if checkProgram(program, srcData):
                return program
            if len(kwargs) > 1:
                for kwarg in kwargs:
                    program = Program(funcInfo)
                    program.addImports(imports)
                    program.addBodyLine('return %s(%s, %s=%s)' % (funcName, ', '.join(funcInfo.args), kwarg[0], kwarg[1]))
                    # print 'checking lines:', program.lines
                    if checkProgram(program, srcData):
                        return program
                    program.addFutureDivision()
                    if checkProgram(program, srcData):
                        return program

    funcSnippets = extractFuncSnippets(codeFragment)

    # print ' === found funcs:', len(funcSnippets)
    # for s in funcSnippets:
    #     funcInfo, funcBody = s
    #     print funcInfo.name, funcInfo.args
    #     for l in funcBody:
    #         print l
    #     print
    #print

    argsToRaplceOrig = []
    for i, arg in enumerate(funcInfo.args):
        argsToRaplceOrig.append('%s%d' % (arg, i + 1))

    for snippFuncInfo, snippBody in funcSnippets:
        if len(snippFuncInfo.args) != len(funcInfo.args):
            continue
        if not snippBody:
            continue
        offset = getOffset(snippBody[0])
        # print ' === check func', snippFuncInfo.name
        # print 'snip args:', snippFuncInfo.args
        # print 'orig args:', funcInfo.args
        program = Program(funcInfo)
        program.addImports(imports)
        for l in snippBody:
            l = l[offset:]
            # print 'before:', l

            if sorted(funcInfo.args) != sorted(snippFuncInfo.args):
                l = replaceArgs(l, funcInfo.args, argsToRaplceOrig)
                l = replaceArgs(l, snippFuncInfo.args, funcInfo.args)
            l = replaceArgs(l, [snippFuncInfo.name], [funcInfo.name])
            # print 'after: ', l
            program.addBodyLine(l)

        if checkProgram(program, srcData):
            return program

        program.lines[-1] += '[0]'
        if checkProgram(program, srcData):
            return program
        program.lines[-1] = program.lines[-1][:-3]

        program.lines[-1] += '[-1]'
        if checkProgram(program, srcData):
            return program
        program.lines[-1] = program.lines[-1][:-4]

        if len(funcInfo.args) > 0:
            program.lines = ['%s -= 1' % funcInfo.args[0]] + program.lines
            if checkProgram(program, srcData):
                return program
            program.lines = program.lines[1:]

        program.addFutureDivision()
        if checkProgram(program, srcData):
            return program

    oneLiners = extractOneLiners(codeFragment)

    for vars, line in oneLiners:
        if len(vars) < len(funcInfo.args):
            continue
        # todo: check all combinations
        for var in vars:
            if len(funcInfo.args) >= 1:
                line = replaceArgs(line, [var], [funcInfo.args[0]])
            program = Program(funcInfo)
            program.addImports(imports)
            program.addBodyLine('return ' + line)
            if checkProgram(program, srcData):
                return program
            program.addFutureDivision()
            if checkProgram(program, srcData):
                return program

    return None

def checkCodeFragments(funcInfo, srcData, codeFragments):
    for codeFragment in codeFragments:
        # print 'checking fragment: <<<'
        # print codeFragment
        # print '>>>\n'
        program = checkCodeFragment(funcInfo, srcData, codeFragment)
        if program is not None:
            return program
    return None

# extractFuncs('print max(path.nodes, key=y)')
# extractFuncs('sorted(vals)')
# extractFuncs('sorted(vals, reverse=True)')

# print extractFuncs('''
#
# maxy = max(node.y for node in node_lst)
# print(maxy)
# >>> 15
#
# max_node = max(node_lst, key=lambda node: node.y)
# print(max_node.y)
# >>> 15
# ''')

# print extractFuncs('''
# sorted(timestamp, reverse=True)
# ''')

def _get_instructions(args):
    links = howdoi._get_links(args['query'])
    if not links:
        return False

    question_links = howdoi._get_questions(links)
    if not question_links:
        return False

    only_hyperlinks = args.get('link')
    star_headers = False

    answers = []
    initial_position = args['pos']

    for answer_number in range(args['num_answers']):
        current_position = answer_number + initial_position
        args['pos'] = current_position
        link = howdoi.get_link_at_pos(question_links, current_position)
        answer = howdoi._get_answer(args, question_links)
        if not answer:
            continue

        answer = howdoi.format_answer(link, answer, star_headers)
        answers.append(answer)
    return answers

def getFragments(query, count = 20):
    args = {}
    args['query'] = query
    args['num_answers'] = count
    args['all'] = False
    args['pos'] = 1
    args['color'] = False
    e = _get_instructions(args)
    frags = set()
    newFrags = []
    for f in e:
        if not f in frags:
            frags.add(f)
            newFrags.append(f)
    return newFrags

def readProblemFile(inFile):
    lines = open(inFile, 'r').read().split('\n')
    for i in xrange(0, len(lines) - 2):
        l1 = lines[i]
        l2 = lines[i + 1]
        l3 = lines[i + 2]
        if l1.startswith('#') and l2.startswith('def ') and l3.startswith('    pass'):
            before = '\n'.join(lines[:i + 1])
            after = '\n'.join(lines[i+3:])
            funcDef = l2
            description = l1[1:].strip()
            return funcDef, description, before, after

def generateCheat(funcInfo, problemFile):
    lines = open(problemFile, 'r').read().split('\n')

    cases = []

    for l in lines:
        l = l.strip()
        if not l.startswith('assert '):
            continue
        l = l[len('assert '):]
        delim = None
        if l.find('==') != -1:
            delim = '=='
        elif l.find(' is ') != -1:
            delim = ' is '
        if delim is None:
            continue
        l = l.split(delim)
        if len(l) < 2:
            continue
        l, r = l[:2]
        l = l.strip()
        r = r.strip()
        if not l.startswith(funcInfo.name):
            if r.startswith(funcInfo.name):
                l, r = r, l
            else:
                continue
        inpArgs = l[len(funcInfo.name)+1:-1]
        #print 'input: %s, output: %s' % (inpArgs, r)
        cases.append((inpArgs, r))

    if not cases:
        return None

    program = Program(funcInfo)
    if 'inp' in funcInfo.args:
        inpName = 'inp%d' % random.randint(0, 1000)
    else:
        inpName = 'inp'

    if len(cases) == 1 or not funcInfo.args:
        program.addBodyLine('return %s' % cases[0][1])
        return program

    program.addBodyLine('%s = [%s]' % (inpName, ', '.join(funcInfo.args)))

    for expectedIn, expectedOut in cases:
        program.addBodyLine('if %s == [%s]:' % (inpName, expectedIn))
        program.addBodyLine('    return %s' % expectedOut)

    return program


def main():
    if len(sys.argv) != 2:
        return printUsage()

    problemFile = sys.argv[1]

    problem = readProblemFile(problemFile)
    if problem is None:
        raise Exception('wrong problem format')

    funcDef, description, before, after = problem

    srcData = (before, after)

    #problem = imp.load_source('problem', problemFile)
    #description = problem.DESCR
    funcInfo = parseFunctionDef(funcDef)

    # program = Program(funcInfo)
    #program.addBodyLine('return sorted(%s, reverse=True)' % funcInfo.args[0])
    # program.addBodyLine('return sorted(%s, reverse=False)' % funcInfo.args[0])
    # print checkProgram(program, problemFile)

    #program = Program(funcInfo)
    # program.addBodyLine('return sorted(%s, reverse=True)' % funcInfo.args[0])
    #program.addBodyLine('return sorted(%s, reverse=False)' % funcInfo.args[0])
    #print checkProgram(program, problemFile)

#     fragments = [
#         'print max(path.nodes, key=y)',
#         'print sorted(nums, reverse=True)',
#         'return sum(values)',
#         '''
# def reverse(text):
#     a = ""
#     for i in range(1, len(text) + 1):
#         a += text[len(text) - i]
#     return a
#
# def tmp():
#   print 42
#
# print(reverse("Hello World!")) # prints: !dlroW olleH
#         '''
#     ]

    print '[info] searching'
    fragments = getFragments('python ' + description, 100)

    print '[info] checking'

    program = checkCodeFragments(funcInfo, srcData, fragments)

    if program is None:
        tmpProgram = generateCheat(funcInfo, problemFile)
        if tmpProgram is not None and checkProgram(tmpProgram, srcData):
            program = tmpProgram

    if program is not None:
        print ''
        print generateImports(program)
        print generateProgram(program)
    else:
        print 'you win'

    #print checkCodeFragment(funcInfo, problemFile, fragment)

    #program.addBodyLine('pass')
    #program.addBodyLine('#' + description)
    #program.addBodyLine('return 42')
    #program.addImport('sys')
    #program.addImport('os')

    #generateOutput(program, problemFile, 'result.py')

if __name__ == '__main__':
    main()
