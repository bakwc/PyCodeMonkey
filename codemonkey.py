#!/usr/bin/env python

import sys
import os
import imp
import time
from subprocess import Popen, PIPE

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

def generateOutput(program, inFile, outFile):
    inData = open(inFile, 'r').read()
    outData = ''
    for importName in program.imports:
        outData += 'import %s\n' % importName
    outData += '\n'

    funcInfo = program.funcInfo

    outData += 'def %s(%s):\n' % (funcInfo.name, ','.join(funcInfo.args))
    for line in program.lines:
        outData += '    %s\n' % line
    outData += '\n\n'
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

def checkCodeFragment(program, inFile, codeFragment):
    pass

def main():
    if len(sys.argv) != 2:
        return printUsage()

    problemFile = sys.argv[1]
    problem = imp.load_source('problem', problemFile)
    description = problem.DESCR
    funcInfo = parseFunctionDef(problem.DEF)

    program = Program(funcInfo)
    program.addBodyLine('return sorted(%s, reverse=True)' % funcInfo.args[0])
    # program.addBodyLine('return sorted(%s, reverse=False)' % funcInfo.args[0])
    print checkProgram(program, problemFile)

    program = Program(funcInfo)
    # program.addBodyLine('return sorted(%s, reverse=True)' % funcInfo.args[0])
    program.addBodyLine('return sorted(%s, reverse=False)' % funcInfo.args[0])
    print checkProgram(program, problemFile)

    #program.addBodyLine('pass')
    #program.addBodyLine('#' + description)
    #program.addBodyLine('return 42')
    #program.addImport('sys')
    #program.addImport('os')

    #generateOutput(program, problemFile, 'result.py')

if __name__ == '__main__':
    main()
