#!/usr/bin/env python

import sys
import os
import imp
import time
from subprocess import Popen, PIPE
from howdoi import howdoi

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

def generateProgram(program):
    outData = ''
    for importName in program.imports:
        outData += 'import %s\n' % importName
    outData += '\n'

    funcInfo = program.funcInfo

    outData += 'def %s(%s):\n' % (funcInfo.name, ', '.join(funcInfo.args))
    for line in program.lines:
        outData += '    %s\n' % line
    return outData

def generateOutput(program, inFile, outFile):
    inData = open(inFile, 'r').read()
    outData = generateProgram(program)
    outData += inData
    outData += '\n'
    outData += '''
if __name__ == '__main__':
    tests()
'''
    open(outFile, 'w').write(outData)
    assert open(outFile, 'r').read() == outData

def checkProgram(program, inFile):
    generateOutput(program, inFile, OUT_FILE)
    process = Popen(["python", "result.py"], stderr=PIPE, stdout=PIPE)
    (output, err) = process.communicate()
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

def checkCodeFragment(funcInfo, inFile, codeFragment):
    funcs = extractFuncs(codeFragment)
    if not funcs:
        return None
    for funcName, args, kwargs in funcs:
        #print 'checking func', funcName

        program = Program(funcInfo)
        program.addBodyLine('return %s(%s)' % (funcName, ', '.join(funcInfo.args)))
        #print 'checking lines:', program.lines
        if checkProgram(program, inFile):
            return program

        if kwargs:
            program = Program(funcInfo)
            program.addBodyLine('return %s(%s, %s)' % (funcName, ', '.join(funcInfo.args), ', '.join([x[0] + '=' + x[1] for x in kwargs])))
            #print 'checking lines:', program.lines
            if checkProgram(program, inFile):
                return program
            if len(kwargs) > 1:
                for kwarg in kwargs:
                    program = Program(funcInfo)
                    program.addBodyLine('return %s(%s, %s=%s)' % (funcName, ', '.join(funcInfo.args), kwarg[0], kwarg[1]))
                    # print 'checking lines:', program.lines
                    if checkProgram(program, inFile):
                        return program

    return None

def checkCodeFragments(funcInfo, inFile, codeFragments):
    for codeFragment in codeFragments:
        # print 'checking fragment: <<<'
        # print codeFragment
        # print '>>>\n'
        program = checkCodeFragment(funcInfo, inFile, codeFragment)
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
    return e


def main():
    if len(sys.argv) != 2:
        return printUsage()

    problemFile = sys.argv[1]
    problem = imp.load_source('problem', problemFile)
    description = problem.DESCR
    funcInfo = parseFunctionDef(problem.DEF)

    # program = Program(funcInfo)
    #program.addBodyLine('return sorted(%s, reverse=True)' % funcInfo.args[0])
    # program.addBodyLine('return sorted(%s, reverse=False)' % funcInfo.args[0])
    # print checkProgram(program, problemFile)

    #program = Program(funcInfo)
    # program.addBodyLine('return sorted(%s, reverse=True)' % funcInfo.args[0])
    #program.addBodyLine('return sorted(%s, reverse=False)' % funcInfo.args[0])
    #print checkProgram(program, problemFile)

    # fragments = [
    #     'print max(path.nodes, key=y)',
    #     'print sorted(nums, reverse=True)',
    #     'return sum(values)',
    # ]

    fragments = getFragments('python ' + description, 10)

    program = checkCodeFragments(funcInfo, problemFile, fragments)
    if program is not None:
        print generateProgram(program)
    else:
        print 'go hack yourself'

    #print checkCodeFragment(funcInfo, problemFile, fragment)

    #program.addBodyLine('pass')
    #program.addBodyLine('#' + description)
    #program.addBodyLine('return 42')
    #program.addImport('sys')
    #program.addImport('os')

    #generateOutput(program, problemFile, 'result.py')

if __name__ == '__main__':
    main()
