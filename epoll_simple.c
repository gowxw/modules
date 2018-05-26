#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/epoll.h>
#include <pthread.h>
#define MAX_EVENTS_NUMBER 1024
#define TCP_BUFFER_SIZE 512
#define UDP_BUFFER_SIZE 1024

int setnonblocking(int fd)
{
	int old_option = fcntl(fd,F_GETFL);
	int new_option = old_option | O_NONBLOCK;
	fcntl(fd,F_SETFL,new_option);
	return old_option;
}

int addfd(int epollfd,int fd)
{
        int ret=0;
	struct epoll_event event;
	event.data.fd = fd;
	event.events = EPOLLIN | EPOLLET;
	ret = epoll_ctl(epollfd,EPOLL_CTL_ADD,fd,&event);
        
        if (ret<0) printf("ret= %d errno=%s\n",ret,strerror(errno));
	setnonblocking(fd);
}

int main(int argc,char * argv[])
{
	if(argc <=2){
		printf("usage: %s ip_address port_number\n",argv[0]);
	}
	const char* ip = argv[1];
	int port = atoi(argv[2]);
	int ret = 0;
	struct sockaddr_in address;
	bzero(&address,sizeof(address));
	address.sin_family = AF_INET;
	inet_pton(AF_INET,ip,&address.sin_addr);
	address.sin_port = htons(port);
	int listenfd = socket(AF_INET,SOCK_STREAM,0);

    if(listenfd<0){
    	exit(0);
    }

    ret = bind(listenfd,(struct sockaddr*)&address,sizeof(address));
    if(ret<0){
    	exit(0);
    }

    ret = listen(listenfd,512);
    if(ret<0){
    	exit(0);
    }



    bzero(&address,sizeof(address));
    address.sin_family = AF_INET;
    inet_pton(AF_INET,ip,&address.sin_addr);
    address.sin_port = htons(port);
    int udp_fd = socket(PF_INET,SOCK_DGRAM,0);
    if(udp_fd<0){
    	exit(0);
    }
    ret = bind(udp_fd,(struct sockaddr*)&address,sizeof(address));
    if(ret<0){
    	exit(0);
    }

    struct epoll_event events[MAX_EVENTS_NUMBER];
    int epollfd = epoll_create(5);
    if(epollfd<0){
    	exit(0);
    }

    addfd(epollfd,listenfd);
    addfd(epollfd,udp_fd);

    while(1){
	int i = 0;
    	int num = epoll_wait(epollfd,events,MAX_EVENTS_NUMBER,3000);
    		if(num < 0){
    			printf("epoll fail");
    			break;
    		}
    		for(i=0;i<num;i++){
    			int sockfd = events[i].data.fd;
                        printf("listenfd=%d sockfd=%d\n",listenfd,sockfd);
    			if(sockfd == listenfd){
    				struct sockaddr_in client_address;
    				socklen_t client_addrlength = sizeof(client_address);
    				int connfd = accept(listenfd,(struct sockaddr*)&client_address,&client_addrlength);
    				addfd(epollfd,connfd);
                                printf("accept %d:0x%x\n",connfd,client_address.sin_addr.s_addr);

    			}else if(sockfd == udp_fd){
    				char buf[UDP_BUFFER_SIZE];
    				memset(buf,'\0',UDP_BUFFER_SIZE);
    				struct sockaddr_in client_address;
    				socklen_t client_addrlength = sizeof(client_address);
    			}else if(events[i].events & EPOLLIN){
    				char buf[TCP_BUFFER_SIZE];
    				while(1){
    					memset(buf,'\0',TCP_BUFFER_SIZE);
    					ret = recv(sockfd,buf,TCP_BUFFER_SIZE-1,0);
    					if(ret<0){
    						if((errno == EAGAIN)||(errno == EWOULDBLOCK)){
    							printf("read finish\n");
    							break;
    						}
    						close(sockfd);
    						break;
    					}else if(ret == 0){
						printf("client closed\n");
    						close(sockfd);
    					}else{
    						printf("recv:%s\n",buf);
					}

    				}

    			}else{
    				printf("something else happed\n");
    			}
    		}


    	}
    

    close(listenfd);


}
