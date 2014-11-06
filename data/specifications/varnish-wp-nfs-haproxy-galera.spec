#Varnish:Active >= 1
and #(_){_ : #Galera:Active > 0 and #Wordpress:ActiveWithNfs > 0 } = 0
and #(_){_ : #Nfs_server:Active > 0 and #Wordpress:ActiveWithNfs > 0 } = 0
and #(_){_ : #Haproxy:Active < 1 and #Wordpress:ActiveWithNfs > 0 } = 0
and #(_){_ : #Wordpress:ActiveWithNfs > 1 } = 0
and #(_){_ : #Galera:Active > 1 } = 0
and 
at{server11@aeiche.innovation.mandriva.com}(#(debian,debian_stub_package) = 1)and
at{server12@aeiche.innovation.mandriva.com}(#(debian,debian_stub_package) = 1)and
at{server13@aeiche.innovation.mandriva.com}(#(debian,debian_stub_package) = 1)and
at{server14@aeiche.innovation.mandriva.com}(#(debian,debian_stub_package) = 1)and
at{server21@aeiche.innovation.mandriva.com}(#(mbs,mbs_stub_package) = 1)and
at{server23@aeiche.innovation.mandriva.com}(#(mbs,mbs_stub_package) = 1)and
at{server24@aeiche.innovation.mandriva.com}(#(mbs,mbs_stub_package) = 1)and
at{server25@aeiche.innovation.mandriva.com}(#(mbs,mbs_stub_package) = 1)
