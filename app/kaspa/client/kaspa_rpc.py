import grpc
from grpc.experimental import dynamic_stub

from app.kaspa.client import rpc_pb2


class KaspaRPCClient:
    def __init__(self, target: str):
        self.channel = grpc.insecure_channel(target)

        # Create dynamic stub from service descriptor
        service_desc = rpc_pb2.DESCRIPTOR.services_by_name["RPC"]
        self.stub = dynamic_stub.DynamicStub(
            self.channel,
            service_desc,
        )

    def get_node_info(self):
        return self.stub.GetInfo(rpc_pb2.GetInfoRequest())

    def get_dag_info(self):
        return self.stub.GetBlockDagInfo(
            rpc_pb2.GetBlockDagInfoRequest()
        )
