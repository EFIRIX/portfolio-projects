addEventListener('DOMContentLoaded', function(){
    var body = document.querySelector('body')
    var topics = document.getElementsByClassName('video_topics')
    var bodies = document.getElementsByClassName('video_body')
    var buts = document.getElementsByClassName('show_button')
    var n = topics.length
    for(let i = 0; i < n; i++){
        topics[i].id = `topic_${i}`
        bodies[i].style.display = 'none'
        bodies[i].id = `vids_${i}`
        buts[i].id = i
    }
    body.addEventListener('click', function(event){
        if (event.target.classList.contains('show_button')){
            let k = event.target.id
            var videos = document.getElementById('vids_'+k)
            if (videos.style.display == 'none'){
                event.target.style = 'transform: rotate(90deg); animation: 0.5s rotate;'
                videos.style.display = 'flex'
            } else {
                event.target.style = 'transform: rotate(0deg);animation: 0.5s rotate_back;'
                videos.style.display = 'none'
            }
        }
    })
    
    const vid = document.createElement('video')
    const video_path ='./NXbkyGCNoO6ytyJGEG1e.mp4'
    vid.style.height = '300px'
    vid.src = video_path
    vid.controls = true
    bodies[i].append(vid)
    .catch(error => console.error('Ошибка:', error));
})