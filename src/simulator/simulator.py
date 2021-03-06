#!/usr/bin/env python2

import argparse
import gv
import random
import sys
import time

# use the parser to generate wtf.py
sys.path.append('.')
import wtf
import chan

class glob:
    render = None
    console = None

def log(s):
    print >> glob.console, '%s' % (s)

def torender(s):
    print >> glob.render, '%s' % (s)
    glob.render.flush()

# Special IDs used to catch unconnected output actions
class StaticID:
    ENVIRONMENT = -1

class EnAction:
    def __init__(self, src, an, ty, dest):
        self.aname = an
        self.atype = ty
        self.src = src
        self.dst = dest

        # input actions only
        self.data = None

    def __repr__(self):
        s = '<EnAction; name: %s, type: %s, src: %s, dst: %s >' \
            % (self.aname, self.atype, str(self.src), str(self.dst))
        return s

    def isinput(self):
        return self.data is not None

class SNode:
    def __init__(self, gid, name, obj, ac, ta):
        self.myid = gid
        self.name = name
        self.obj = obj
        self.actions = ac
        self.tasks = ta
        self.weights = {}

        # channel only fields
        self.chanid = None

        # a map of action names to pairs of (i, j) where i is the destination
        # SNode and j is the action of the node corresponding to dest SNode
        self.omap = {}
        self.nbrs = {}

    def addweight(self, to, weight):
        self.weights[to.myid] = weight

    def conn_output(self, srcac, destsn, dstac):
        if srcac not in self.actions:
            raise ValueError('%s is not an action for %s' % (srcac, self.name))
        assert self.actions[srcac]['atype'] == 'output'

        om = self.omap
        destpair = (destsn, dstac)
        if om.has_key(srcac):
            om[srcac].append(destpair)
        else:
            om[srcac] = [destpair]

        self.nbrs[destsn.tranid('out')] = True

    def ischannel(self):
        return self.chanid is not None

    def getenabled(self):
        '''
        returns list of EnActions. if the atype of the action is 'output', dest
        is the destination id of the enabled output action.
        '''

        actions = self.actions
        tasks = self.tasks

        ret = []
        for ct in tasks:
            action = actions[ct]

            # input actions never have preconditions
            atype = action['atype']
            assert atype != 'input'

            arity = action['arityprec']

            if atype == 'internal':
                assert arity == 0
                if action['prec']():
                    ret.append(EnAction(self.myid, ct, atype, 0))
                continue

            # must be an output action
            if ct not in self.omap:
                raise ValueError('output %s is not connected?' % (ct))

            oputnbrs = [x[0] for x in self.omap[ct]]
            # -1 because we provide the dest id
            arity -= 1
            for tf in oputnbrs:
                args = [tf.tranid('out')] + [0 for i in range(arity)]

                if apply(action['prec'], args):
                    ret.append(EnAction(self.myid, ct, atype, tf.myid))

        return ret

    def namefor(self, myactname, dst):
        for i in self.omap[myactname]:
            if i[0].myid == dst:
                return i[1]
        return None

    def Nbrs(self):
        # special ids
        spec = [-1]
        return filter(lambda x: x not in spec, [x for x in self.nbrs])

    def tranid(self, d):
        '''
        gets the id of the node which is suitable for transition code (ie if
        the SNode is a channel, don't return the id of the channel but the id
        of the node at the end of the channel
        '''
        if d not in ['in', 'out']:
            s = 'bad direction for tranid: %s' % (d)
            raise ValueError(s)
        if self.ischannel():
            if d == 'in':
                return self.chanid[0]
            else:
                return self.chanid[1]
        return self.myid

class Net:

    def __init__(self):
        self.nodes = {}
        self.name2id = {}
        self.envsn = SNode(StaticID.ENVIRONMENT, None, None, None, None)
	self.inactions = []

    def __repr__(self):
        s = ''
        for sn in self.nodes.values():
            s += 'Node: %s\n' % (sn.name)
            for n in sn.Nbrs():
                s += '\t%s\n' % (self.node(n).name)

        return s

    def addnode(self, i, sn):
        self.name2id[sn.name] = i
        self.nodes[i] = sn

    def node(self, i):
        return self.nodes[i]

    def nodeid(self, name):
        return self.name2id[name]

    def addedge(self, ssn, srcaction, dsn, dstaction):
        sn = self.nodes[ssn.myid]
        sn.conn_output(srcaction, dsn, dstaction)
        if dsn.myid == StaticID.ENVIRONMENT:
            return
        sn = self.nodes[dsn.myid]
        assert sn.actions[dstaction]['atype'] == 'input'

    def doenaction(self, ea, st = 0):

        sn = self.nodes[ea.src]
        action = sn.actions[ea.aname]
        if ea.atype == 'internal':
            assert action['arityeff'] == 0
            action['eff']()
            return None

        # must be output action
        dn = self.nodes[ea.dst]
        arity = action['arityoutput']
        inaction = dn.actions[sn.namefor(ea.aname, ea.dst)]
        assert arity == inaction['arityeff']

        # arity-1 since we provide dest, the rest are dummy args (should not
        # generate them in the parser?)
        did = ea.dst
        if did != StaticID.ENVIRONMENT:
            did = self.node(did).tranid('out')
        args = [did] + [0 for i in range(arity - 1)]
        output = apply(action['output'], args)
        apply(action['eff'], args)

        # provide the output as input to the appropriate automaton
        if ea.dst == StaticID.ENVIRONMENT:
            log('Output to env: %s' % (str(output)))
            return None

	dstname = self.node(dn.tranid('out')).name
	srcname = self.node(sn.tranid('in')).name

	if dn.ischannel():
            torender('send %s %s "%s"' % (srcname, dstname,
	      "%s(%s)" % (ea.aname, output)))
        self.doinput(ea, output)

    def doinput(self, inact, output):
        sn = self.nodes[inact.src]
        dn = self.nodes[inact.dst]

        inactname = sn.namefor(inact.aname, inact.dst)
        inaction = dn.actions[inactname]
        args = [self.node(inact.src).tranid('in')] + [output]
        apply(inaction['eff'], args)

        dstname = self.node(dn.tranid('out')).name
        srcname = self.node(sn.tranid('in')).name

        if not dn.ischannel():
            torender('recv %s %s' % (dstname, srcname))

    def simstarting(self, m):
        n = self.N()
        for i in self.nodes.values():
            def mark(msg, node=i):
                m('mark %s "%s"' % (node.name, msg))
            def label(msg, node=i):
                m('label %s "%s"' % (node.name, msg))
            def emark(to, color, msg, node=i):
                m('emark %s %s "%s" "%s"' % (node.name, self.node(to).name, color, msg))

            i.obj.N = n
            i.obj.weights = i.weights
            i.obj.nbrs = i.Nbrs()
            i.obj.markcb = mark
            i.obj.labelcb = label
            i.obj.emarkcb = emark
            i.obj.init()

    def getenabledall(self):
        return reduce(lambda x, y: x + y, [self.nodes[x].getenabled() for x in self.nodes])

    def step(self):
        acs = self.getenabledall()

        if not acs:
            log('no enabled actions')
            return False

        nextaction = random.choice(acs)
        self.doenaction(nextaction)

        return True

    def manualinput(self, nodeid, actionname, fr, msg):
        ac = self.node(nodeid).actions[actionname]
        assert ac['arityeff'] == 2
        assert ac['atype'] == 'input'
        ac['eff'](fr, msg)

    def N(self):
        n = len([n for n in self.nodes if not self.nodes[n].ischannel()])
        # print warning if fishy stuff
        eyes = [x.obj.i for x in self.nodes.values()]
        ns = range(len(self.nodes)+1)
        for i in eyes:
            if i not in ns:
                print '*Warning: missing an ID'

        return n

class Nbuilder:
    def __init__(self, filename, randid, usechan=True):
        self.fn = filename
        self.randid = randid
        self.usechan = usechan
        self.chancount = 0

    def go(self):
        g = gv.read(self.fn)
        if not g:
            s = "couldn't open/parse %s" % (self.fn)
            raise ValueError(s)

        net = Net()

        if len(wtf.allclasses) > 1:
            s = ('simulator only works with one automaton' +
                ' but you have %d defined in your spec' % len(wtf.allclasses))
            raise ValueError(s)

        # generate all nodes
        allclass = wtf.allclasses
        chanclass = chan.allclasses['Channel']
        k = allclass.keys()[0]
        n = gv.firstnode(g)
        ns = 0
        while n:
            ns = ns + 1
            n = gv.nextnode(g, n)

        ids = range(ns)
        if self.randid:
            random.shuffle(ids)

        n = gv.firstnode(g)
        ni = 0
        while n:
            auto = allclass[k]()
            name = gv.nameof(n)

            idd = ids[ni]
            auto.i = idd
            ni = ni + 1

            net.addnode(idd, SNode(idd, name, auto, \
              auto.actions(), auto.tasks()))
            n = gv.nextnode(g, n)

        # add all edges
        e = gv.firstedge(g)
        while e:
            f = net.node(net.nodeid(gv.nameof(gv.tailof(e))))
            t = net.node(net.nodeid(gv.nameof(gv.headof(e))))
            w = gv.getv(e, 'weight')
            w = float(w) if w else 0

            for outp, inp in f.obj.connectout.iteritems():
                # insert channel
                if self.usechan:
                    c = self.chansnode(f.myid, t.myid)
                    net.addnode(c.myid, c)
                    # XXX weird. src out -> chan in, chan out -> dst in
                    cout = c.obj.connectout.keys()[0]
                    cin = c.obj.connectout.values()[0]
                    net.addedge(f, outp, c, cin)
                    net.addedge(c, cout, t, inp)
                    f.addweight(t, w)
                else:
                    raise ValueError('no imp')

            e = gv.nextedge(g, e)

        return net

    def chansnode(self, fid, tid):
        ret = chan.allclasses['Channel']()
        ret.init()
        n = 'chan_%d' % (self.chancount)
        self.chancount += 1
        ret = SNode(n, n, ret, ret.actions(), ret.tasks())
        ret.chanid = (fid, tid)
        return ret

def ioinit(graphfile, trace):
    import os
    import subprocess
    # start renderer
    args = [os.path.join(
        os.path.dirname(sys.argv[0]),
        '..',
        'renderer',
        'bin',
        'renderer'
        )]

    if trace:
        args.append("-t")
    args.append(graphfile)

    renderer = subprocess.Popen(args,
        stdin=subprocess.PIPE,
        stdout=sys.stderr)
    glob.render = renderer.stdin
    # automata prints go to stdout
    # simulator prints go to stderr
    glob.console = sys.stderr

def btest(graphfile, lim, st, randid, trace):

    ioinit(graphfile, trace)

    fn = graphfile
    log('reading %s...' % (fn))
    n = Nbuilder(fn, randid).go()

    #print n
    n.simstarting(lambda x: torender(x))
    #n.manualinput(0, 'read', 0, 'herro there!')
    i = 0
    while n.step():
        i += 1
	if i >= lim:
		break
        glob.render.flush()
        if st:
            time.sleep(st)

    sys.stdout = sys.stderr
    raw_input("Simulation ended; press enter to close renderer.")
    log('done')

def maintest():

    ioinit()

    chanc = chan.allclasses['Channel']
    n = Net()
    no = chanc()
    no.init()
    n.addnode('flea', SNode('flea', 'Channel-0', no, no.actions(), no.tasks()))

    no = chanc()
    no.init()
    n.addnode(no.i, SNode(1, 'Channel-1', no, no.actions(), no.tasks()))

    assert n.node('flea').obj.i == 0
    assert n.node(1).obj.i == 1

    for o, i in n.node('flea').obj.connectout.iteritems():
        n.addedge(n.node('flea'), o, n.node(1), i)
    for o in n.node(1).obj.connectout:
        n.addedge(n.node(1), o,
          SNode(StaticID.ENVIRONMENT, None, None, None, None), 'dur')

    n.simstarting(lambda x: torender(x))
    print n.getenabledall()
    print 'sending message...'
    n.nodes['flea'].actions['send']['eff'](StaticID.ENVIRONMENT, 'duh hello!')
    print n.getenabledall()
    n.step()
    print n.getenabledall()
    n.step()
    print n.getenabledall()

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Simulate the operation of a network of I/O automata.')
    parser.add_argument('-g', '--graph', required=True,
            help='Simulate the automaton operating on GRAPH')
    parser.add_argument('-l', '--limit', type=int, default=1000,
            help='Simulate for LIMIT steps')
    parser.add_argument('-s', '--sleep', type=float, default=0.0,
            help='Sleep for this number of seconds between steps')
    parser.add_argument('-r', '--random-ids', action='store_true',
            help='Randomize the ID of each simulated node')
    parser.add_argument('-t', '--trace', action='store_true',
            help='Keep all intermediary step visualizations')
    args = parser.parse_args()
    btest(args.graph, args.limit, args.sleep, args.random_ids, args.trace)
    #maintest()
