import json
import re
from flask import Flask, jsonify, request
from flask_cors import CORS
from py2neo import Graph
from http import HTTPStatus
import dashscope
app = Flask(__name__)
CORS(app,supports_credentials=True)


def get_data_list(text):
    '''
    数据处理
    :param text:
    :return:
    '''
    try:
        data_dict = json.loads(text)
    except:
        try:
            data_dict = eval(text)
        except:
            try:
                result = re.findall(r'\[(.*?)\]', text.replace('\n', ''))
                if result and len(result) == 1:
                    data_dict = eval('[' + result[0] + ']')
                else:
                    data_dict = []
            except:
                data_dict = []
    return data_dict

class neo4j_db():
    '''neo4j的操作'''

    def __init__(self):
        self.graph = Graph(
            host="127.0.0.1",  # neo4j 搭载服务器的ip地址，ifconfig可获取到
            port=7687,  # neo4j 服务器监听的端口号
            user="neo4j",  # 数据库user name，如果没有更改过，应该是neo4j
            password="123456789")

        sql = 'MATCH (n) RETURN DISTINCT labels(n) AS labels'
        result = self.graph.run(sql)
        self.label_lists = []
        for lin in result:
            self.label_lists.append(lin[0][0])

        with open('data/label.json', 'r', encoding='utf-8') as f:
            self.label_list = json.load(f)

        self.prompt = "【指令】根据已知信息，简洁和专业的来回答问题。如果无法从中得到答案，可以适当的发挥想象，答案请使用中文。\n\
                      \n【已知信息】{{context}}\n\n【问题】{{question}}\n"

        self.prompt_ = '''
# 背景
你是一个信息抽取专家
# 任务
可以根据一段历史对话，抽取该段话的实体和关系，并形成三元组形式
# 数据结构设计
{label_json}
# 要求
1 尽可能抽取准确,必须从文本中抽取相关信息，不能随意发挥
2 不要抽取和数据结构设计之外的数据类型和关系类型
3 必须选择数据结构设计列表中的一个{"start_label": "xxx", "rel": "xxx", "end_label": "xx"},并抽取的实体变成
{"start_label": "xxx","start_entity":'xxx', "rel": "xxx", "end_label": "xx","end_entity":"xxx"}
4 如果没有足够数据那就不用抽取,抽取主要是user说法里面，而不是assistant,assistant里面不要抽取
# 示例
输入：
{input}
输出：
[{"start_label": "xxx","start_entity":'xxx', "rel": "xxx", "end_label": "xx","end_entity":"xxx"},....]

'''

        sql = 'MATCH (n) RETURN n.name as name,labels(n) AS labels'
        result = self.graph.run(sql)
        self.entity_dict = {}
        for lin in result:
            self.entity_dict[lin['name']] = lin['labels'][0]
        self.entity_list = [lin for lin in self.entity_dict]



    def chat_(self, question,total_history):
        '''
        多路检索获取答案
        :param question:
        :return:
        '''
        # 动态生成知识图谱
        result = self.llm_extra_kg(str(total_history))
        result_list = get_data_list(result)
        self.data_import(result_list)


        # 文生cypher
        cypher = self.llm_extra_cypher(question)
        try:
            context_ = self.cypher_chat(cypher)
        except:
            context_ = ''

        entity = ''
        #  实体识别
        max_len = 0
        for lin in self.entity_list:
            if lin in question and len(lin) > max_len:
                entity = lin
                max_len = len(lin)
        if entity:
            context_ = context_+ self.chat_neo4j(entity)
            answer = self.llm_extra(question,context_)
        else:
            answer = self.llm_extra(question,'')
        return answer

    def cypher_chat(self, cypher):
        '''
        cypher查询
        :param question:
        :return:
        '''
        #  实体识别
        result = self.graph.run(cypher).data()
        return str(result)

    def data_import(self,result_list):
        '''
        数据导入
        :return:
        '''
        #  实体识别
        print(result_list)
        sqls = []
        try:
            for lin in result_list:
                if lin['start_entity'] and lin['end_entity']:
                    sqls.append('merge (n:%s{name:"%s"})' % (lin['start_label'], lin['start_entity']))
                    sqls.append('merge (n:%s{name:"%s"})' % (lin['end_label'], lin['end_entity']))
                    sqls.append(
                        'match (p:%s),(q:%s) where p.name="%s" and q.name="%s" merge (p)-[rel:%s]->(q)' % (
                            lin['start_label'], lin['end_label'], lin['start_entity'], lin['end_entity'], lin['rel']))

            for sql in sqls:
                self.graph.run(sql)

            sql = 'MATCH (n) RETURN n.name as name,labels(n) AS labels'
            result = self.graph.run(sql)
            self.entity_dict = {}
            for lin in result:
                self.entity_dict[lin['name']] = lin['labels'][0]
            self.entity_list = [lin for lin in self.entity_dict]
        except :
            pass


    def chat_neo4j(self, entity):
        '''问答流程'''

        context = ''
        #  知识问答
        sql = "match p=(n)-[r]-(m) where n.name='%s' return m.name as name,type(r) as rname"%(entity)
        result = self.graph.run(sql).data()

        if result:
            for lin in result:
                if not context:
                    context = entity+'的'+lin['rname']+'为'+lin['name']+'\n'
                else:
                    context = context+'，'+entity+'的'+lin['rname']+'为'+lin['name']+'\n'

        return context

    def llm_extra(self,question,context):
        '''
        这里换成本地模型
        :param text:
        :param prompt:
        :return:
        '''
        print('context',context)
        print('question',question)
        from http import HTTPStatus
        import dashscope
        # dashscope.api_key = ''
        dashscope.api_key = 'sk-54258b163ca04dca92130c0ab98e62c0'
        messages = [{'role': 'user', 'content': self.prompt.replace('{context}', context).replace('{question}', question)}]
        try:
            response = dashscope.Generation.call(
                "qwen-long",
                messages=messages,
                result_format='message',  # set the result to be "message" format.
            )
        except:
            print('调用qwen模型失败')
            return '目前无法回复你的问题'
        if response.status_code == HTTPStatus.OK:

            return response['output']['choices'][0]['message']['content']
        else:
            print('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))
            return '目前无法回复你的问题'


    def llm_extra_cypher(self,question):
        '''
        这里换成本地模型
        :param text:
        :param prompt:
        :return:
        '''
        prompt = '''
        # neo4j含有实体类型为：
        互救能力,公众,具体事故,危险源,地质与地震灾害,
        应急手册,应急技能,应急措施,应急类别,急救方法,报警电话
        突发事件,紧急情况,自救能力,防护知识
        # neo4j 含有关系为：
        使用,包含,包括,引发,掌握,涉及,需要,预防
        
        # 根据question问题生成cypher语句，只要输出cypher语句即可，不要输出其他内容
        
        {{question}}
        
        '''
        # dashscope.api_key = 'sk-6b9d0adadea742b5a2410fc8058f9d84'
        dashscope.api_key = 'sk-54258b163ca04dca92130c0ab98e62c0'
        messages = [{'role': 'user', 'content': prompt.replace('{{question}}', question)}]
        try:
            response = dashscope.Generation.call(
                "qwen-long",
                messages=messages,
                result_format='message',  # set the result to be "message" format.
            )
        except:
            print('调用qwen模型失败')
            return '目前无法回复你的问题'
        if response.status_code == HTTPStatus.OK:

            return response['output']['choices'][0]['message']['content']
        else:
            print('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))
            return '目前无法回复你的问题'

    def llm_extra_kg(self, input):
        '''
        这里换成本地模型
        :param text:
        :param prompt:
        :return:
        '''

        # dashscope.api_key = 'sk-6b9d0adadea742b5a2410fc8058f9d84'
        dashscope.api_key = 'sk-54258b163ca04dca92130c0ab98e62c0'
        messages = [{'role': 'user', 'content': self.prompt_.replace('{label_json}', str(self.label_list)).replace('{input}',input)}]
        try:
            response = dashscope.Generation.call(
                "qwen-long",
                messages=messages,
                result_format='message',  # set the result to be "message" format.
            )
        except:
            print('调用qwen模型失败')
            return '目前无法回复你的问题'
        if response.status_code == HTTPStatus.OK:

            return response['output']['choices'][0]['message']['content']
        else:
            print('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))
            return '目前无法回复你的问题'



neo4j_handle = neo4j_db()

@app.route('/api/tryChat', methods=['GET', 'POST'])
def tryChat():

    json_data = request.json
    content_list = json_data['content']
    user_history,bot_history = [],[]
    total_history = []
    for lin in content_list:
        text = lin['text']
        if lin['type']=='user':
            user_history.append(text)
            total_history.append({'role': 'user', 'content': text})
        else:
            bot_history.append(text)
            total_history.append({'role': 'assistant', 'content': text})
    answer = neo4j_handle.chat_(user_history[-1],total_history)
    print(str(total_history))
    return jsonify(answer)



if __name__ == '__main__':
    app.run()
    # app.run(debug=True)
