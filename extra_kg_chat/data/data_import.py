import json
from py2neo import Graph
from tqdm import tqdm


class import_db(object):
    '''知识图谱导入'''

    def __init__(self):
        self.g = Graph(
            host="127.0.0.1",  # neo4j 搭载服务器的ip地址，ifconfig可获取到
            port=7687,  # neo4j 服务器监听的端口号
            user="neo4j",  # 数据库user name，如果没有更改过，应该是neo4j
            password="123456789")

    def import_data(self):
        sqls = ['match (n) detach delete n']

        data_list = []

        with open('result.json', 'r', encoding='utf-8') as f:
            data_list += json.load(f)

        total_list = []
        for data in data_list:
            result = data['result']
            for li in result:
                try:
                    total_list.append(
                        {'start_entity': li['start_entity'], 'start_label': li['start_label'], 'end_label': li['end_label'],
                         'end_entity': li['end_entity'],
                         'rel': li['rel']})
                except:
                    continue
        for lin in total_list:
            sqls.append('merge (n:%s{name:"%s"})' % (lin['start_label'], lin['start_entity']))
            sqls.append('merge (n:%s{name:"%s"})' % (lin['end_label'], lin['end_entity']))
            sqls.append(
                'match (p:%s),(q:%s) where p.name="%s" and q.name="%s" merge (p)-[rel:%s]->(q)' % (
                    lin['start_label'], lin['end_label'], lin['start_entity'], lin['end_entity'], lin['rel']))

        for sql in tqdm(sqls):
            # 批量导入
            try:
                self.g.run(sql)
            except Exception as e:
                # print(e)
                continue


if __name__ == '__main__':
    #  入口文件
    handel = import_db()
    handel.import_data()
